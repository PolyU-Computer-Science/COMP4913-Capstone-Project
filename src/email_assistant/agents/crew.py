from functools import cached_property

from crewai import Agent, Crew, LLM, Process, Task
from crewai.llms.base_llm import BaseLLM

from email_assistant.core.stage_defaults import effective_stage_settings
from email_assistant.core.settings_store import SettingsStore
from email_assistant.models import EmailClassification
from email_assistant.service import LLMSettings, create_llm, load_llm_settings


class EmailAssistant:
    """EmailAssistant crew (classification + drafting).

    Stage configuration (role/goal/backstory/prompt + generation params)
    lives in the settings DB, seeded once from built-in defaults. There is
    no YAML config; the DB is the single source of truth.
    """

    def __init__(self) -> None:
        self._store = SettingsStore()

    @cached_property
    def base_settings(self) -> LLMSettings:
        """The active AI config (or env fallback) as LLM settings."""
        return load_llm_settings()

    def _stage(self, stage: str) -> dict:
        return effective_stage_settings(stage, self._store.get_stage_settings(stage))

    def _stage_llm(self, stage: str) -> BaseLLM:
        """Build an LLM with per-stage temperature / max_tokens overrides."""
        stage_settings = self._stage(stage)
        updates: dict = {}
        if stage_settings.get("temperature") is not None:
            updates["temperature"] = float(stage_settings["temperature"])
        if stage_settings.get("max_tokens") is not None:
            updates["max_tokens"] = int(stage_settings["max_tokens"])
        return create_llm(self.base_settings.model_copy(update=updates))

    @cached_property
    def classifier_llm(self) -> BaseLLM:
        return self._stage_llm("classification")

    @cached_property
    def drafter_llm(self) -> BaseLLM:
        return self._stage_llm("draft")

    def classifier(self) -> Agent:
        s = self._stage("classification")
        return Agent(
            role=s["role"],
            goal=s["goal"],
            backstory=s["backstory"],
            llm=self.classifier_llm,
            verbose=True,
        )

    def drafter(self) -> Agent:
        s = self._stage("draft")
        return Agent(
            role=s["role"],
            goal=s["goal"],
            backstory=s["backstory"],
            llm=self.drafter_llm,
            verbose=True,
        )

    def classify_email_task(self) -> Task:
        s = self._stage("classification")
        return Task(
            description=s["prompt"],
            expected_output=(
                "A structured classification object with category (question, "
                "incident, problem, task, or spam), topic, priority, "
                "summary, and custom field values."
            ),
            agent=self.classifier(),
            output_pydantic=EmailClassification,
        )

    def draft_reply_task(self) -> Task:
        s = self._stage("draft")
        return Task(
            description=s["prompt"],
            expected_output=(
                "The reply body text only, plain text, ready to send. Start "
                "with the greeting and end with a sign-off, in the same "
                "language as the sender's latest message."
            ),
            agent=self.drafter(),
            context=[self.classify_email_task()],
        )

    def draft_only_crew(self) -> Crew:
        """Creates a drafting-only crew.

        Used when classification already ran through the structured runtime
        (``StructuredClassifier``): the validated classification JSON is
        interpolated into the draft prompt via the ``classification`` input,
        so no in-crew classifier call is needed.
        """
        return Crew(
            agents=[self.drafter()],
            tasks=[
                Task(
                    description=self._stage("draft")["prompt"],
                    expected_output=(
                        "The reply body text only, plain text, ready to send. "
                        "Start with the greeting and end with a sign-off, in "
                        "the same language as the sender's latest message."
                    ),
                    agent=self.drafter(),
                )
            ],
            process=Process.sequential,
            verbose=True,
        )

    def crew(self) -> Crew:
        """Creates the EmailAssistant crew"""
        return Crew(
            agents=[self.classifier(), self.drafter()],
            tasks=[self.classify_email_task(), self.draft_reply_task()],
            process=Process.sequential,
            verbose=True,
        )
