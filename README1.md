# SalesCode.ai Challenge: LiveKit Interrupt Handler

Branch: feature/livekit-interrupt-handler-VaibhavMeena

This branch contains the solution for the LiveKit Voice Interruption Handling Challenge.

## What Changed

To solve the challenge, I implemented an "extension layer" within the basic_agent.py example by using event listeners. No core SDK code was modified.

- basic_agent.py: This file was modified to include the new logic.
-  AgentSession(min_interruption_words=1): I set this parameter in the session. This was the key to preventing the VAD from pausing the agent before the STT had a chance to transcribe the word. This forces the agent to wait for at least one word, giving my logic time to run.
-  session.agent_is_speaking State: I added a boolean state variable session.agent_is_speaking to track whether the agent's TTS is active.
-  session.on("agent_state_changed"): This new event handler updates the session.agent_is_speaking variable to True when the agent's state is "speaking" and False otherwise.
-  session.on("user_input_transcribed"): This is the core logic handler.
   - It checks if session.agent_is_speaking is True.
   - If it is, it checks the incoming transcript against a IGNORED_WORDS set (e.g., {"uh", "umm", "hmm", "haan"}).
   - If the transcript only contains filler words, it calls session.clear_user_turn() to immediately cancel the interruption and allow the agent to continue speaking seamlessly.
   - If the transcript contains any real words (like "stop" or "wait"), it does nothing, allowing the interruption to proceed normally.

## What Works

The solution successfully meets all objectives:
- Filler Words Ignored: While the agent is speaking, saying "umm," "hmm," or "haan" is ignored, and the agent continues speaking without a pause.
- Real Interruptions Handled: While the agent is speaking, saying "stop," "wait," or any non-filler word immediately and correctly interrupts the agent.
- Fillers While Quiet: If the agent is quiet, saying "umm" or "hmm" is correctly registered as user speech, and the agent responds to it.

## Known Issues

None observed during testing. The solution appears robust for both filler-only and mixed (e.g., "umm, wait") interruptions.

## Steps to Test

- Install Dependencies:
  Set up and activate a virtual environment
  python -m venv venv
  .\venv\Scripts\activate

  Install the library and example dependencies
  pip install -e .
  pip install -r examples/voice_agents/requirements.txt
- Set Up Environment:

Copy .env.example to .env.

Fill in your LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, and OPENAI_API_KEY.

Download Models:

python examples/voice_agents/basic_agent.py download-files


Run the Agent:

python examples/voice_agents/basic_agent.py console


Verify the Fix:

Test 1 (Filler): Get the agent to talk (e.g., "tell me a story"). While it's speaking, say "umm." The agent should continue speaking without pausing.

Test 2 (Real Interruption): Get the agent to talk. While it's speaking, say "stop." The agent should immediately stop and listen.

Test 3 (Quiet Filler):An: Wait for the agent to be quiet. Say "hmm." The agent should hear this as valid input and respond (e.g., "How can I help you?").

Environment Details

Python: 3.12 (but should work on 3.9+)

Main Package: livekit-agents (installed from the repository)

Plugins: livekit-plugins-silero, livekit-plugins-turn-detector

Services: AssemblyAI (STT), OpenAI (LLM), Cartesia (TTS)
