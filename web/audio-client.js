// Browser-based Audio Client for OpenAI Realtime API
// Handles microphone capture and audio playback in the browser

class BrowserAudioClient {
  constructor(backendUrl, apiKey) {
    this.backendUrl = backendUrl;
    this.apiKey = apiKey;
    this.ws = null;
    this.audioContext = null;
    this.mediaStream = null;
    this.audioWorkletNode = null;
    this.isRecording = false;
    this.isMuted = false;

    // Audio playback worklet
    this.ttsWorkletNode = null;
    this.isTTSPlaying = false;

    // Callbacks
    this.onStatusChange = null;
    this.onTranscript = null;
    this.onResponse = null;
    this.onError = null;

    // Agent creation context tracking
    this.agentCreationContext = {
      inProgress: false,
      tool: null,
      agentType: null,
      agentName: null
    };

    // Operator file polling for Agent Zero tasks
    this.operatorFilePollers = new Map(); // agentName -> { operatorFile, interval }
  }

  async initialize() {
    try {
      // Create audio context - browser will choose best sample rate (usually 48kHz)
      // We'll resample as needed
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)();

      this.log('info', `🔊 Audio context initialized: ${this.audioContext.sampleRate} Hz`);

      // Load AudioWorklet for TTS playback
      await this.audioContext.audioWorklet.addModule('ttsPlaybackProcessor.js');
      this.ttsWorkletNode = new AudioWorkletNode(
        this.audioContext,
        'tts-playback-processor'
      );

      // Listen for playback events
      this.ttsWorkletNode.port.onmessage = (event) => {
        if (event.data.type === 'ttsPlaybackStarted') {
          this.isTTSPlaying = true;
          console.log('TTS playback started');
        } else if (event.data.type === 'ttsPlaybackStopped') {
          this.isTTSPlaying = false;
          console.log('TTS playback stopped');
        }
      };

      // Connect worklet to audio output
      this.ttsWorkletNode.connect(this.audioContext.destination);

      // Request microphone access
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: { ideal: 24000 },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      this.log('info', '🎤 Microphone access granted');
      return true;
    } catch (error) {
      console.error('Failed to initialize audio:', error);
      if (this.onError) this.onError('Microphone access denied: ' + error.message);
      return false;
    }
  }

  async connect() {
    return new Promise((resolve, reject) => {
      try {
        this.log('info', '🔌 Connecting to backend: ' + this.backendUrl);

        this.ws = new WebSocket(this.backendUrl);
        this.ws.binaryType = 'arraybuffer';

        this.ws.onopen = () => {
          this.log('info', '✅ WebSocket connected');
          if (this.onStatusChange) this.onStatusChange('connected');

          // Send session configuration
          this.sendSessionUpdate();

          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          if (this.onError) this.onError('Connection error');
          reject(error);
        };

        this.ws.onclose = () => {
          console.log('WebSocket closed');
          if (this.onStatusChange) this.onStatusChange('disconnected');
          this.stopRecording();
        };

      } catch (error) {
        console.error('Failed to connect:', error);
        reject(error);
      }
    });
  }

  sendSessionUpdate() {
    const sessionConfig = {
      type: 'session.update',
      session: {
        modalities: ['text', 'audio'],
        instructions: `You are a voice-controlled AI assistant that manages multiple AI agents.

CRITICAL: You have function tools available. You MUST use them when users ask about agents.

User says "list agents" → Call list_agents() function immediately
User says "create agent" → Call create_agent() function
User says "command agent X to do Y" → Call command_agent() function
User says "delete agent X" → Call delete_agent() function

DO NOT provide information about Siri, Alexa, Google Assistant, or other virtual assistants. Those are NOT the agents you manage.

The agents YOU manage are:
- Claude Code agents (for software development)
- Gemini agents (for web browsing)
- Agent Zero agents (for general tasks)

When a user asks anything about "agents", they mean the AI agents in YOUR system. Always use your function tools to manage them.`,
        voice: 'alloy',
        temperature: 0.6,
        input_audio_format: 'pcm16',
        output_audio_format: 'pcm16',
        input_audio_transcription: {
          model: 'whisper-1'
        },
        turn_detection: {
          type: 'server_vad',
          threshold: 0.5,
          prefix_padding_ms: 300,
          silence_duration_ms: 500
        },
        tools: this.getToolsSchema()
      }
    };

    this.log('info', `📤 Sending session config with ${sessionConfig.session.tools.length} tools`);
    this.send(sessionConfig);
  }

  getToolsSchema() {
    return [
      {
        type: 'function',
        name: 'create_agent',
        description: 'Create a new AI agent (Claude Code for coding, Gemini for browser automation, or Agent Zero for general tasks)',
        parameters: {
          type: 'object',
          properties: {
            tool: {
              type: 'string',
              enum: ['claude_code', 'gemini', 'agent_zero'],
              description: 'Type of agent to create'
            },
            agent_type: {
              type: 'string',
              description: 'Agent type (agentic_coding, agentic_browsing, agentic_general)'
            },
            agent_name: {
              type: 'string',
              description: 'Unique name for the agent'
            },
            lifetime_hours: {
              type: 'number',
              description: 'How many hours the agent should live (default 24)',
              default: 24
            }
          },
          required: ['tool', 'agent_type', 'agent_name']
        }
      },
      {
        type: 'function',
        name: 'list_agents',
        description: 'ALWAYS call this when user asks to "list agents", "show agents", "what agents", or similar queries about viewing all agents. Returns list of all active AI agents and their current status.',
        parameters: {
          type: 'object',
          properties: {}
        }
      },
      {
        type: 'function',
        name: 'command_agent',
        description: 'Send a command or instruction to an existing agent',
        parameters: {
          type: 'object',
          properties: {
            agent_name: {
              type: 'string',
              description: 'Name of the agent to command'
            },
            prompt: {
              type: 'string',
              description: 'Command or instruction for the agent'
            }
          },
          required: ['agent_name', 'prompt']
        }
      },
      {
        type: 'function',
        name: 'delete_agent',
        description: 'Delete an agent and remove it from the registry',
        parameters: {
          type: 'object',
          properties: {
            agent_name: {
              type: 'string',
              description: 'Name of the agent to delete'
            }
          },
          required: ['agent_name']
        }
      },
      {
        type: 'function',
        name: 'get_agent_status',
        description: 'Get detailed status and metadata for an agent',
        parameters: {
          type: 'object',
          properties: {
            agent_name: {
              type: 'string',
              description: 'Name of the agent to query'
            }
          },
          required: ['agent_name']
        }
      }
    ];
  }

  async startRecording() {
    if (this.isRecording) return;

    try {
      const source = this.audioContext.createMediaStreamSource(this.mediaStream);

      // Create a script processor for audio capture
      const bufferSize = 4096;
      const processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

      processor.onaudioprocess = (e) => {
        if (!this.isMuted && this.ws && this.ws.readyState === WebSocket.OPEN) {
          const inputData = e.inputBuffer.getChannelData(0);

          // Convert Float32Array to Int16Array (PCM16)
          const pcm16 = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            const s = Math.max(-1, Math.min(1, inputData[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }

          // Send audio data to backend
          this.sendAudio(pcm16.buffer);
        }
      };

      source.connect(processor);
      processor.connect(this.audioContext.destination);

      this.audioWorkletNode = processor;
      this.isRecording = true;

      this.log('info', '🎙️ Recording started');
      if (this.onStatusChange) this.onStatusChange('recording');

    } catch (error) {
      console.error('Failed to start recording:', error);
      if (this.onError) this.onError('Failed to start recording: ' + error.message);
    }
  }

  stopRecording() {
    if (this.audioWorkletNode) {
      this.audioWorkletNode.disconnect();
      this.audioWorkletNode = null;
    }
    this.isRecording = false;
    console.log('Recording stopped');
  }

  sendAudio(audioData) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      // Convert to base64
      const base64 = this.arrayBufferToBase64(audioData);

      const message = {
        type: 'input_audio_buffer.append',
        audio: base64
      };

      this.send(message);
    }
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  sendText(text) {
    const message = {
      type: 'conversation.item.create',
      item: {
        type: 'message',
        role: 'user',
        content: [{
          type: 'input_text',
          text: text
        }]
      }
    };

    this.send(message);

    // Request response
    this.send({ type: 'response.create' });
  }

  async executeFunctionCall(callId, functionName, argsJson) {
    try {
      this.log('info', `⚙️ Executing function: ${functionName}`);

      // Parse arguments
      const args = JSON.parse(argsJson || '{}');

      // Call the Python backend to execute the function
      let result;
      switch (functionName) {
        case 'list_agents':
          result = await eel.ui_list_agents()();
          break;
        case 'create_agent':
          result = await eel.ui_create_agent(args.tool, args.agent_type, args.agent_name, args.lifetime_hours || 24)();
          break;
        case 'command_agent':
          result = await eel.ui_command_agent(args.agent_name, args.prompt)();
          break;
        case 'delete_agent':
          result = await eel.ui_delete_agent(args.agent_name)();
          break;
        case 'get_agent_status':
          result = await eel.ui_get_agent_status(args.agent_name)();
          break;
        default:
          this.log('error', `Unknown function: ${functionName}`);
          result = { ok: false, error: 'Unknown function' };
      }

      this.log('info', `✅ Function result:`, result);

      // Add observability event
      this.addObservabilityEvent({
        type: `function_${functionName}`,
        function_name: functionName,
        arguments: args,
        result: result,
        timestamp: new Date().toISOString()
      });

      // Send function result back to OpenAI
      const functionOutput = {
        type: 'conversation.item.create',
        item: {
          type: 'function_call_output',
          call_id: callId,
          output: JSON.stringify(result)
        }
      };

      this.send(functionOutput);

      // Request a new response with the function result
      this.send({ type: 'response.create' });

    } catch (error) {
      this.log('error', `Failed to execute function: ${functionName}`, error.message);

      // Send error back to OpenAI
      const errorOutput = {
        type: 'conversation.item.create',
        item: {
          type: 'function_call_output',
          call_id: callId,
          output: JSON.stringify({ ok: false, error: error.message })
        }
      };

      this.send(errorOutput);
      this.send({ type: 'response.create' });
    }
  }

  async detectAndExecuteFunctionFromText(text) {
    try {
      // Skip detection for system-generated messages (those starting with emoji indicators)
      const systemPrefixes = ['🗑️', '✅', '❌', '📋', '🎯', '🤖', '⚠️'];
      if (systemPrefixes.some(prefix => text.startsWith(prefix))) {
        this.log('info', '⏭️ Skipping detection for system message');
        return;
      }

      const lowerText = text.toLowerCase();

      // Detect list agents request
      if (lowerText.includes('checking agents') || lowerText.includes('list agents') || lowerText.includes('show agents')) {
        this.log('info', '🤖 Detected list agents request from text');
        const result = await eel.ui_list_agents()();
        this.log('info', '📋 Agent list:', result);

        // Format and send results to AI
        if (result.ok && result.agents) {
          const agentSummary = result.agents.length === 0
            ? '📋 No agents currently active.'
            : `📋 Found ${result.agents.length} agent(s):\n` + result.agents.map(a =>
                `• ${a.name} (${a.tool}, ${a.type})`
              ).join('\n');

          // Send to AI so it can speak the results
          this.sendText(agentSummary);

          // Add observability event
          this.addObservabilityEvent({
            type: 'agent_list',
            count: result.agents.length,
            agents: result.agents.map(a => a.name),
            timestamp: new Date().toISOString()
          });
        }
        return;
      }

      // Track agent creation context
      if (lowerText.includes('what kind of agent') || lowerText.includes('which one')) {
        this.agentCreationContext.inProgress = true;
        this.agentCreationContext.tool = null;
        this.agentCreationContext.agentType = null;
        this.agentCreationContext.agentName = null;
        this.log('info', '🔄 Started agent creation flow');
        return;
      }

      // Detect create agent request - try to parse details
      if (lowerText.includes('creating') && lowerText.includes('agent')) {
        this.log('info', '🤖 Detected create agent request from text');

        // Try to extract agent name from the current response
        const nameMatch = text.match(/(?:named?|called?)\s+([a-zA-Z0-9_-]+)/i);
        let agentName = nameMatch ? nameMatch[1] : this.agentCreationContext.agentName;

        // Try to detect tool type from current response or context
        let tool = this.agentCreationContext.tool;
        if (lowerText.includes('claude_code') || lowerText.includes('claude code')) {
          tool = 'claude_code';
        } else if (lowerText.includes('gemini')) {
          tool = 'gemini';
        } else if (lowerText.includes('agent_zero') || lowerText.includes('agent zero')) {
          tool = 'agent_zero';
        }

        // Try to detect agent type from current response or context
        let agentType = this.agentCreationContext.agentType;
        if (lowerText.includes('coding')) {
          agentType = 'agentic_coding';
        } else if (lowerText.includes('browsing')) {
          agentType = 'agentic_browsing';
        } else if (lowerText.includes('general')) {
          agentType = 'agentic_general';
        }

        // Auto-infer agent type from tool if not specified
        if (tool && !agentType) {
          if (tool === 'claude_code') agentType = 'agentic_coding';
          else if (tool === 'gemini') agentType = 'agentic_browsing';
          else if (tool === 'agent_zero') agentType = 'agentic_general';
        }

        // If we have all required info, create the agent
        if (tool && agentType && agentName) {
          this.log('info', `✨ Creating ${tool} agent: ${agentName} (${agentType})`);

          try {
            const result = await eel.ui_create_agent(tool, agentType, agentName, 24)();
            this.log('info', '✅ Agent created:', result);

            if (result.ok) {
              this.log('info', `🎉 Successfully created agent: ${agentName}`);

              // Add observability event
              this.addObservabilityEvent({
                type: 'agent_created',
                agent_name: agentName,
                tool: tool,
                agent_type: agentType,
                source: 'voice_text_detection',
                timestamp: new Date().toISOString()
              });

              // Reset context
              this.agentCreationContext.inProgress = false;
              this.agentCreationContext.tool = null;
              this.agentCreationContext.agentType = null;
              this.agentCreationContext.agentName = null;
            }
          } catch (error) {
            this.log('error', 'Failed to create agent', error);
          }
        } else {
          this.log('info', '💡 Need more details - missing:',
            !tool ? 'tool' : '',
            !agentType ? 'type' : '',
            !agentName ? 'name' : ''
          );
        }
        return;
      }

      // Update context when user provides tool choice
      if (this.agentCreationContext.inProgress && !this.agentCreationContext.tool) {
        if (lowerText.includes('claude_code') || lowerText.includes('claude code')) {
          this.agentCreationContext.tool = 'claude_code';
          this.agentCreationContext.agentType = 'agentic_coding';
          this.log('info', '📝 Recorded tool choice: claude_code');
        } else if (lowerText.includes('gemini')) {
          this.agentCreationContext.tool = 'gemini';
          this.agentCreationContext.agentType = 'agentic_browsing';
          this.log('info', '📝 Recorded tool choice: gemini');
        } else if (lowerText.includes('agent_zero') || lowerText.includes('agent zero')) {
          this.agentCreationContext.tool = 'agent_zero';
          this.agentCreationContext.agentType = 'agentic_general';
          this.log('info', '📝 Recorded tool choice: agent_zero');
        }
      }

      // Update context when user provides name
      if (this.agentCreationContext.inProgress && this.agentCreationContext.tool &&
          lowerText.includes('what should we name')) {
        // Next user input will be the name - we'll capture it in the user input event
        this.agentCreationContext.waitingForName = true;
        this.log('info', '⏳ Waiting for agent name...');
      }

      // Detect command agent request
      if (lowerText.includes('command') && lowerText.includes('to')) {
        this.log('info', '🤖 Detected command agent request from text');

        // Try to extract agent name and command
        // Pattern: "tell <agent> to <command>" or "command <agent> to <command>"
        const commandMatch = text.match(/(?:tell|command)\s+(\w+)\s+to\s+(.+)/i);

        if (commandMatch) {
          const agentName = commandMatch[1];
          const prompt = commandMatch[2];

          this.log('info', `📤 Commanding agent "${agentName}": ${prompt}`);

          try {
            const result = await eel.ui_command_agent(agentName, prompt)();
            this.log('info', '✅ Command sent:', result);

            if (result.ok) {
              this.log('info', `🎯 Successfully commanded ${agentName}`);

              // Add observability event
              this.addObservabilityEvent({
                type: 'agent_command',
                agent_name: agentName,
                prompt: prompt.substring(0, 100),
                source: 'voice_text_detection',
                timestamp: new Date().toISOString()
              });

              // Start polling operator file if one was created
              if (result.operator_file) {
                this.startOperatorFilePolling(agentName, result.operator_file);
              }
            }
          } catch (error) {
            this.log('error', 'Failed to command agent', error);
          }
        }
        return;
      }

      // Detect delete agent request
      // Patterns: "delete agent", "remove agent", "delete all", "remove them"
      const isDeleteRequest = (lowerText.includes('delet') || lowerText.includes('remov')) &&
                               (lowerText.includes('agent') || lowerText.includes('them') ||
                                lowerText.includes('all') || lowerText.includes('every'));

      if (isDeleteRequest) {
        this.log('info', '🤖 Detected delete agent request from text');

        // Check if user wants to delete ALL agents
        // "them" refers to all agents mentioned in context
        if (lowerText.includes('all') || lowerText.includes('every') || lowerText.includes('them')) {
          this.log('info', '🗑️ Deleting ALL agents');

          try {
            // Get list of all agents first
            const listResult = await eel.ui_list_agents()();
            if (listResult.ok && listResult.agents) {
              const agents = listResult.agents;
              this.log('info', `Found ${agents.length} agents to delete`);

              let deletedCount = 0;
              let failedCount = 0;

              // Delete each agent
              for (const agent of agents) {
                try {
                  const result = await eel.ui_delete_agent(agent.name)();
                  if (result.ok) {
                    deletedCount++;
                    this.log('info', `✅ Deleted agent: ${agent.name}`);

                    // Add observability event
                    this.addObservabilityEvent({
                      type: 'agent_deleted',
                      agent_name: agent.name,
                      source: 'voice_text_detection',
                      timestamp: new Date().toISOString()
                    });
                  } else {
                    failedCount++;
                    this.log('error', `Failed to delete ${agent.name}: ${result.error}`);
                  }
                } catch (error) {
                  failedCount++;
                  this.log('error', `Error deleting ${agent.name}:`, error);
                }
              }

              // Send summary to AI
              const summary = `🗑️ Deleted ${deletedCount} agent(s)${failedCount > 0 ? `, ${failedCount} failed` : ''}`;
              this.sendText(summary);
            }
          } catch (error) {
            this.log('error', 'Failed to delete all agents', error);
          }
          return;
        }

        // Try to extract specific agent name
        // Patterns: "delete agent <name>", "remove <name>", "delete <name>"
        let agentName = null;

        const patterns = [
          /(?:delet|remov)e?\s+agent\s+(\w+)/i,  // "delete agent cheff"
          /(?:delet|remov)e?\s+(\w+)\s+agent/i,  // "delete cheff agent"
          /agent\s+(\w+)\s+(?:delet|remov)/i,    // "agent cheff delete"
          /(?:delet|remov)e?\s+(\w+)/i           // "delete cheff"
        ];

        for (const pattern of patterns) {
          const match = text.match(pattern);
          if (match) {
            const candidate = match[1];
            // Skip generic words
            if (!['agent', 'agents', 'all', 'the'].includes(candidate.toLowerCase())) {
              agentName = candidate;
              break;
            }
          }
        }

        if (agentName) {
          this.log('info', `🗑️ Deleting agent: ${agentName}`);

          try {
            const result = await eel.ui_delete_agent(agentName)();
            this.log('info', '✅ Delete result:', result);

            if (result.ok) {
              this.log('info', `🎯 Successfully deleted agent: ${agentName}`);

              // Add observability event
              this.addObservabilityEvent({
                type: 'agent_deleted',
                agent_name: agentName,
                source: 'voice_text_detection',
                timestamp: new Date().toISOString()
              });

              // Send confirmation to AI
              this.sendText(`✅ Agent "${agentName}" has been deleted`);
            } else {
              this.sendText(`❌ Failed to delete agent "${agentName}": ${result.error}`);
            }
          } catch (error) {
            this.log('error', 'Failed to delete agent', error);
          }
        } else {
          this.log('info', '⚠️ No specific agent name detected');
        }
        return;
      }

      // Detect get agent status request
      if ((lowerText.includes('status') || lowerText.includes('check')) && lowerText.includes('agent')) {
        this.log('info', '🤖 Detected agent status request from text');

        // Try to extract agent name with improved patterns
        // Patterns: "status of agent <name>", "check agent <name>", "agent <name> status", "<name> status"
        let agentName = null;

        // Try pattern: "agent <name>" or "status of <name>" or "check <name>"
        const patterns = [
          /agent\s+(\w+)/i,                           // "agent nema"
          /status\s+(?:of\s+)?(?:agent\s+)?(\w+)/i,  // "status of nema" or "status nema"
          /check\s+(?:agent\s+)?status\s+(?:of\s+)?(?:agent\s+)?(\w+)/i, // "check status of agent nema"
          /(\w+)\s+status/i                           // "nema status"
        ];

        for (const pattern of patterns) {
          const match = text.match(pattern);
          if (match) {
            const candidate = match[1];
            // Skip generic words
            if (!['agent', 'status', 'check', 'the', 'of', 'checking'].includes(candidate.toLowerCase())) {
              agentName = candidate;
              break;
            }
          }
        }

        if (agentName) {
          this.log('info', `📊 Getting status for agent: ${agentName}`);

          try {
            const result = await eel.ui_get_agent_status(agentName)();
            this.log('info', '✅ Agent status:', result);

            if (result.ok && result.agent) {
              const agent = result.agent;
              this.log('info', `📋 ${agentName}: ${agent.tool} (${agent.type}) - Created: ${new Date(agent.created_at).toLocaleString()}`);

              // Add observability event
              this.addObservabilityEvent({
                type: 'agent_status_check',
                agent_name: agentName,
                agent_info: agent,
                source: 'voice_text_detection',
                timestamp: new Date().toISOString()
              });
            }
          } catch (error) {
            this.log('error', 'Failed to get agent status', error);
          }
        } else {
          this.log('info', '⚠️ No specific agent name detected for status check');
        }
        return;
      }

    } catch (error) {
      this.log('error', 'Failed to execute detected function', error.message);
    }
  }

  log(level, message, data = null) {
    // Log to browser console
    if (level === 'error') {
      console.error(message, data || '');
    } else {
      console.log(message, data || '');
    }

    // Send to server terminal
    if (typeof eel !== 'undefined' && eel.log_to_server) {
      eel.log_to_server(level, message, data);
    }
  }

  addObservabilityEvent(event) {
    // Call the global addObservabilityEvent function from app-browser.js
    if (typeof window.addObservabilityEvent === 'function') {
      window.addObservabilityEvent(event);
    }
  }

  handleMessage(data) {
    try {
      const event = JSON.parse(data);

      // Log ALL events for debugging (except audio deltas which are too verbose)
      if (!event.type.includes('audio.delta')) {
        this.log('info', `📨 ${event.type}`);
      }

      switch (event.type) {
        case 'session.created':
        case 'session.updated':
          this.log('info', '✅ Session configured');
          const tools = event.session?.tools;
          if (tools) {
            this.log('info', `✅ Server confirmed ${tools.length} tools registered`, tools.map(t => t.name));
          }
          break;

        case 'input_audio_buffer.speech_started':
          this.log('info', '🎤 Speech detected');
          if (this.onStatusChange) this.onStatusChange('speaking');
          break;

        case 'input_audio_buffer.speech_stopped':
          this.log('info', '🎤 Speech ended');
          break;

        case 'conversation.item.created':
          // Log when conversation items are created
          const item = event.item;
          if (item?.content) {
            item.content.forEach(content => {
              if (content.type === 'input_audio' && content.transcript) {
                this.log('info', '📝 Transcript: ' + content.transcript);
                if (this.onTranscript) this.onTranscript(content.transcript);
              } else if (content.type === 'input_text') {
                this.log('info', '📝 Text input: ' + content.text);

                // Capture agent name when waiting for it
                if (this.agentCreationContext.waitingForName && content.text) {
                  this.agentCreationContext.agentName = content.text.trim();
                  this.agentCreationContext.waitingForName = false;
                  this.log('info', `📝 Recorded agent name: ${this.agentCreationContext.agentName}`);
                }
              }
            });
          }
          break;

        case 'conversation.item.input_audio_transcription.completed':
          const transcript = event.transcript;
          this.log('info', '📝 Transcript (completed): ' + transcript);
          if (this.onTranscript) this.onTranscript(transcript);
          break;

        case 'response.function_call_arguments.delta':
          // Accumulate function arguments
          this.log('info', '🔧 Function call delta: ' + event.name);
          break;

        case 'response.function_call_arguments.done':
          // Function call complete - execute it
          const funcName = event.name;
          const funcArgs = event.arguments;
          this.log('info', `🔧 Function call complete: ${funcName}`, JSON.parse(funcArgs || '{}'));

          // Execute the function via Python backend
          this.executeFunctionCall(event.call_id, funcName, funcArgs);
          break;

        case 'response.output_item.added':
          this.log('info', '➕ Output item added', {
            type: event.item?.type,
            role: event.item?.role
          });
          break;

        case 'response.audio.delta':
          // Play audio response (don't log every delta, too verbose)
          this.playAudioChunk(event.delta);
          break;

        case 'response.text.delta':
          if (this.onResponse) this.onResponse(event.delta, false);
          break;

        case 'response.text.done':
          const responseText = event.text || '(empty)';
          this.log('info', '📄 Text response: ' + responseText);
          if (this.onResponse) this.onResponse(event.text, true);

          // Auto-detect function calls from text response (workaround for backend not supporting tool_calls)
          if (event.text) {
            this.detectAndExecuteFunctionFromText(event.text);
          }
          break;

        case 'response.done':
          this.log('info', '✅ Response complete', {
            status: event.response?.status,
            output: event.response?.output?.map(o => ({ type: o.type, role: o.role }))
          });
          if (this.onStatusChange) this.onStatusChange('ready');
          break;

        case 'error':
          this.log('error', '❌ Server error', event.error);
          if (this.onError) this.onError(event.error.message);
          break;

        default:
          // Log function-related events
          if (event.type && event.type.includes('function')) {
            this.log('info', '🔧 Function event: ' + event.type, event);
          }
      }
    } catch (error) {
      this.log('error', 'Failed to parse message', error.message);
    }
  }

  playAudioChunk(base64Audio) {
    try {
      // Decode base64 to ArrayBuffer
      const binaryString = atob(base64Audio);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Convert to Int16Array (PCM16 format)
      const int16Data = new Int16Array(bytes.buffer);

      // Send directly to AudioWorklet for playback
      if (this.ttsWorkletNode) {
        this.ttsWorkletNode.port.postMessage(int16Data);
      }

    } catch (error) {
      console.error('Failed to play audio:', error);
    }
  }

  arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  setMuted(muted) {
    this.isMuted = muted;
    console.log('Microphone', muted ? 'muted' : 'unmuted');
  }

  startOperatorFilePolling(agentName, operatorFile) {
    // Stop any existing poller for this agent
    this.stopOperatorFilePolling(agentName);

    this.log('info', `📊 Started polling operator file for ${agentName}: ${operatorFile}`);

    // Poll every 2 seconds
    const intervalId = setInterval(async () => {
      try {
        const result = await eel.ui_get_operator_file(agentName, operatorFile)();

        if (result.ok) {
          // Check if task is complete
          if (result.is_complete) {
            this.log('info', `✅ Task completed for ${agentName}`);

            // Stop polling
            this.stopOperatorFilePolling(agentName);

            // Add observability event
            this.addObservabilityEvent({
              type: 'agent_task_completed',
              agent_name: agentName,
              operator_file: operatorFile,
              content: result.content.substring(0, 500),  // First 500 chars
              timestamp: new Date().toISOString()
            });

            // Extract just the result section from the operator file
            const resultMatch = result.content.match(/## Result\n([\s\S]+)/);
            let resultSummary = resultMatch ? resultMatch[1].trim() : result.content;

            // Limit to reasonable size
            if (resultSummary.length > 1000) {
              resultSummary = resultSummary.substring(0, 1000) + '... (truncated)';
            }

            // Send completion notification to the AI assistant via conversation context
            const completionMessage = `🎯 Agent "${agentName}" task completed!\n\n${resultSummary}`;

            this.log('info', `📄 Sending completion to AI: ${completionMessage}`);

            // Send as a conversation item so the AI can see it and respond
            this.sendText(completionMessage);
          }
        } else {
          // If file not found or error, stop polling
          this.log('error', `Failed to poll operator file: ${result.error}`);
          this.stopOperatorFilePolling(agentName);
        }
      } catch (error) {
        this.log('error', `Error polling operator file:`, error);
        this.stopOperatorFilePolling(agentName);
      }
    }, 2000);  // Poll every 2 seconds

    // Store the interval ID
    this.operatorFilePollers.set(agentName, {
      operatorFile,
      intervalId
    });
  }

  stopOperatorFilePolling(agentName) {
    const poller = this.operatorFilePollers.get(agentName);
    if (poller) {
      clearInterval(poller.intervalId);
      this.operatorFilePollers.delete(agentName);
      this.log('info', `🛑 Stopped polling operator file for ${agentName}`);
    }
  }

  stopAllOperatorFilePolling() {
    for (const agentName of this.operatorFilePollers.keys()) {
      this.stopOperatorFilePolling(agentName);
    }
  }

  disconnect() {
    this.stopRecording();

    // Stop all operator file polling
    this.stopAllOperatorFilePolling();

    if (this.ttsWorkletNode) {
      this.ttsWorkletNode.port.postMessage({ type: 'clear' });
      this.ttsWorkletNode.disconnect();
      this.ttsWorkletNode = null;
    }

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
  }
}

// Export for use in main app
window.BrowserAudioClient = BrowserAudioClient;
