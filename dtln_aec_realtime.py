"""
Real-time DTLN-aec implementation for streaming audio
Based on https://github.com/breizhn/DTLN-aec

Author: Adapted for real-time use
License: MIT
"""

import numpy as np
import tensorflow.lite as tflite
import os

class DTLNAECRealtime:
    """
    Real-time DTLN-aec processor for echo cancellation.
    Processes audio in streaming fashion with low latency.
    """

    def __init__(self, model_size=128):
        """
        Initialize DTLN-aec for real-time processing.

        Parameters:
        -----------
        model_size : int
            Model size - 128 (fastest), 256 (balanced), or 512 (best quality)
        """
        # Determine model path
        model_dir = os.path.join(os.path.dirname(__file__), 'DTLN-aec', 'pretrained_models')
        model_base = f'dtln_aec_{model_size}'

        # Load TFLite models
        self.interpreter_1 = tflite.Interpreter(
            model_path=os.path.join(model_dir, f'{model_base}_1.tflite')
        )
        self.interpreter_1.allocate_tensors()

        self.interpreter_2 = tflite.Interpreter(
            model_path=os.path.join(model_dir, f'{model_base}_2.tflite')
        )
        self.interpreter_2.allocate_tensors()

        # Get input/output details
        self.input_details_1 = self.interpreter_1.get_input_details()
        self.output_details_1 = self.interpreter_1.get_output_details()
        self.input_details_2 = self.interpreter_2.get_input_details()
        self.output_details_2 = self.interpreter_2.get_output_details()

        # Initialize LSTM states
        self.states_1 = np.zeros(self.input_details_1[1]['shape']).astype('float32')
        self.states_2 = np.zeros(self.input_details_2[1]['shape']).astype('float32')

        # Buffer settings (from original DTLN-aec)
        self.block_len = 512       # FFT size
        self.block_shift = 128     # Hop size - DTLN processes 128 samples at a time

        # Input buffering for variable chunk sizes
        self.input_buffer_mic = []
        self.input_buffer_ref = []
        self.output_buffer_queue = []

        # Initialize buffers
        self.in_buffer = np.zeros(self.block_len).astype('float32')
        self.in_buffer_lpb = np.zeros(self.block_len).astype('float32')
        self.out_buffer = np.zeros(self.block_len).astype('float32')

        # Initialize with padding
        padding = np.zeros(self.block_len - self.block_shift)
        self.in_buffer[:len(padding)] = padding
        self.in_buffer_lpb[:len(padding)] = padding

        print(f"   🤖 DTLN-aec initialized (model size: {model_size})")
        print(f"   ⚡ Block: {self.block_len}, Shift: {self.block_shift}, Latency: ~30ms")

    def process_frame(self, mic_chunk, reference_chunk):
        """
        Process one frame of audio for echo cancellation.
        Handles variable-size chunks by buffering and processing in 128-sample blocks.

        Parameters:
        -----------
        mic_chunk : np.ndarray
            Microphone input (int16, any size but typically 480 samples)
        reference_chunk : np.ndarray
            Speaker output/loopback (int16, same size as mic_chunk)

        Returns:
        --------
        np.ndarray : Echo-cancelled audio (int16, same size as input)
        """
        # Add incoming samples to input buffers
        self.input_buffer_mic.extend(mic_chunk.tolist())
        self.input_buffer_ref.extend(reference_chunk.tolist())

        # Process all complete 128-sample blocks
        while len(self.input_buffer_mic) >= self.block_shift:
            # Extract 128 samples
            mic_block = np.array(self.input_buffer_mic[:self.block_shift], dtype=np.int16)
            ref_block = np.array(self.input_buffer_ref[:self.block_shift], dtype=np.int16)

            # Remove processed samples from buffers
            self.input_buffer_mic = self.input_buffer_mic[self.block_shift:]
            self.input_buffer_ref = self.input_buffer_ref[self.block_shift:]

            # Convert to float32 and normalize
            mic_float = mic_block.astype('float32') / 32768.0
            lpb_float = ref_block.astype('float32') / 32768.0

            # Update buffers (overlap-add)
            self.in_buffer[:-self.block_shift] = self.in_buffer[self.block_shift:]
            self.in_buffer[-self.block_shift:] = mic_float

            self.in_buffer_lpb[:-self.block_shift] = self.in_buffer_lpb[self.block_shift:]
            self.in_buffer_lpb[-self.block_shift:] = lpb_float

            # === FIRST MODEL: Spectral Mask Estimation ===
            # Calculate FFT
            in_block_fft = np.fft.rfft(self.in_buffer).astype('complex64')
            lpb_block_fft = np.fft.rfft(self.in_buffer_lpb).astype('complex64')

            # Calculate magnitudes
            in_mag = np.abs(in_block_fft).reshape(1, 1, -1).astype('float32')
            lpb_mag = np.abs(lpb_block_fft).reshape(1, 1, -1).astype('float32')

            # Set tensors for first model
            # Input order: [mic_magnitude, states, loopback_magnitude]
            self.interpreter_1.set_tensor(self.input_details_1[0]['index'], in_mag)
            self.interpreter_1.set_tensor(self.input_details_1[2]['index'], lpb_mag)
            self.interpreter_1.set_tensor(self.input_details_1[1]['index'], self.states_1)

            # Run first model
            self.interpreter_1.invoke()

            # Get outputs
            out_mask = self.interpreter_1.get_tensor(self.output_details_1[0]['index'])
            self.states_1 = self.interpreter_1.get_tensor(self.output_details_1[1]['index'])

            # Apply mask and IFFT
            estimated_block = np.fft.irfft(in_block_fft * out_mask)

            # === SECOND MODEL: Time-domain Refinement ===
            # Reshape for second model
            estimated_block_reshaped = estimated_block.reshape(1, 1, -1).astype('float32')
            in_lpb_reshaped = self.in_buffer_lpb.reshape(1, 1, -1).astype('float32')

            # Set tensors for second model
            # Input order: [estimated_speech, states, loopback_time_domain]
            self.interpreter_2.set_tensor(self.input_details_2[0]['index'], estimated_block_reshaped)
            self.interpreter_2.set_tensor(self.input_details_2[1]['index'], self.states_2)
            self.interpreter_2.set_tensor(self.input_details_2[2]['index'], in_lpb_reshaped)

            # Run second model
            self.interpreter_2.invoke()

            # Get output
            out_block = self.interpreter_2.get_tensor(self.output_details_2[0]['index'])
            self.states_2 = self.interpreter_2.get_tensor(self.output_details_2[1]['index'])

            # Update output buffer (overlap-add)
            self.out_buffer[:-self.block_shift] = self.out_buffer[self.block_shift:]
            self.out_buffer[-self.block_shift:] = np.zeros(self.block_shift)
            self.out_buffer += np.squeeze(out_block)

            # Extract output frame
            output = self.out_buffer[:self.block_shift].copy()

            # Clip to prevent overflow
            output = np.clip(output, -1.0, 1.0)

            # Convert back to int16
            output_int16 = (output * 32767.0).astype(np.int16)

            # Add to output queue
            self.output_buffer_queue.extend(output_int16.tolist())

        # Return requested number of samples (same as input size)
        output_size = len(mic_chunk)
        if len(self.output_buffer_queue) >= output_size:
            result = np.array(self.output_buffer_queue[:output_size], dtype=np.int16)
            self.output_buffer_queue = self.output_buffer_queue[output_size:]
            return result
        else:
            # Not enough output yet (startup condition), return zeros
            return np.zeros(output_size, dtype=np.int16)

    def reset(self):
        """Reset internal states (useful when conversation starts/stops)"""
        self.states_1 = np.zeros(self.input_details_1[1]['shape']).astype('float32')
        self.states_2 = np.zeros(self.input_details_2[1]['shape']).astype('float32')
        self.in_buffer = np.zeros(self.block_len).astype('float32')
        self.in_buffer_lpb = np.zeros(self.block_len).astype('float32')
        self.out_buffer = np.zeros(self.block_len).astype('float32')
