import logging

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RoomOutputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
    # --- NEW CODE START ---
    # We need these to listen for events and check the agent's state
    UserInputTranscribedEvent,
    AgentStateChangedEvent,
    # --- NEW CODE END ---
)
from livekit.agents.llm import function_tool
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# uncomment to enable Krisp background voice/noise cancellation
# from livekit.plugins import noise_cancellation

logger = logging.getLogger("basic-agent")

load_dotenv()


class MyAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="Your name is Kelly. You would interact with users via voice."
            "with that in mind keep your responses concise and to the point."
            "do not use emojis, asterisks, markdown, or other special characters in your responses."
            "You are curious and friendly, and have a sense of humor."
            "you will speak english to the user",
        )

    async def on_enter(self):
        # when the agent is added to the session, it'll generate a reply
        # according to its instructions
        self.session.generate_reply()

    # all functions annotated with @function_tool will be passed to the LLM when this
    # agent is active
    @function_tool
    async def lookup_weather(
        self, context: RunContext, location: str, latitude: str, longitude: str
    ):
        """Called when the user asks for weather related information.
        Ensure the user's location (city or region) is provided.
        When given a location, please estimate the latitude and longitude of the location and
        do not ask the user for them.

        Args:
            location: The location they are asking for
            latitude: The latitude of the location, do not ask user for it
            longitude: The longitude of the location, do not ask user for it
        """

        logger.info(f"Looking up weather for {location}")

        return "sunny with a temperature of 70 degrees."


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # each log entry will include these fields
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt="assemblyai/universal-streaming:en",
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm="openai/gpt-4.1-mini",
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts="cartesia/sonic-2:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
        # sometimes background noise could interrupt the agent session, these are considered false positive interruptions
        # when it's detected, you may resume the agent's speech
        resume_false_interruption=True,
        false_interruption_timeout=1.0,
        min_interruption_words=1,
    )

    # --- NEW CODE START ---
    # This is your new "extension layer" to handle interruptions
    # ---------------------------------------------------------

    # 1. Define your configurable list of filler words
    # Using a set for faster lookups
    IGNORED_WORDS = {"uh", "umm", "hmm", "haan"}

    # 2. Add a state variable to the session to track agent speech
    session.agent_is_speaking = False

    # 3. Create an event handler to update the agent's state
    @session.on("agent_state_changed")
    def on_agent_state_changed(event: AgentStateChangedEvent):
        """Listen for when the agent starts or stops speaking"""
        if event.new_state == "speaking":
            session.agent_is_speaking = True
        else:
            session.agent_is_speaking = False
        
        logger.debug(f"Agent state is now {event.new_state}")

    # 4. Create your main interruption-handling logic
    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event: UserInputTranscribedEvent):
        """
        This is the core logic. This function is called every time
        the user's speech is transcribed.
        """
        
        # A. If the agent is quiet, do nothing. Let all speech go through.
        # This satisfies the requirement to "register fillers when agent is quiet"
        if not session.agent_is_speaking:
            return

        # B. The agent is speaking, so we must filter the input
        transcript = event.transcript.lower().strip()
        if not transcript:
            return

        # C. Check if the *entire* transcript is just filler words
        words = transcript.split()
        
        # Check if every word in the transcript is in our ignore list
        # We strip punctuation just in case ("umm..." or "hmm?")
        is_only_fillers = all(word.rstrip(".,?!") in IGNORED_WORDS for word in words)

        # D. Take action based on the check
        if is_only_fillers:
            # This is a filler-only interruption.
            logger.info(f"Ignoring filler input: '{transcript}'")
            
            # This is the magic: We tell the session to clear the user's
            # input. This stops the agent from processing the "umm"
            # and allows it to resume speaking much faster (or not pause at all).
            session.clear_user_turn()
        else:
            # This is a REAL interruption (e.g., "wait" or "umm, wait")
            # We do nothing and let the agent get interrupted normally.
            logger.info(f"Valid interruption detected: '{transcript}'")

    # --- NEW CODE END ---


    # log metrics as they are emitted, and total usage after session is over
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    # shutdown callbacks are triggered when the session is over
    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=MyAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # uncomment to enable Krisp BVC noise cancellation
            # noise_cancellation=noise_cancellation.BVC(),
        ),
        room_output_options=RoomOutputOptions(transcription_enabled=True),
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))