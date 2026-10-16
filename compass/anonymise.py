"""Strip names, emails, phone numbers, URLs and company names from chat text.

Uses Microsoft Presidio (NER + pattern recognisers). This is an *offline* tool for the
training-data export; the web app never imports it, so the web app doesn't need Presidio
or a spaCy model installed.

Presidio is statistical, so it will miss some things. Treat the output as reduced-risk,
not anonymous: spot-check it before sharing or training on it.
"""

from collections.abc import Iterable

ENTITIES = [
    "PERSON",
    "ORGANIZATION",  # company names
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "URL",
    "LOCATION",
    "IP_ADDRESS",
    "CREDIT_CARD",
    "IBAN_CODE",
    "UK_NHS",
]
PLACEHOLDERS = {
    "PERSON": "<PERSON>",
    "ORGANIZATION": "<COMPANY>",
    "EMAIL_ADDRESS": "<EMAIL>",
    "PHONE_NUMBER": "<PHONE>",
    "URL": "<URL>",
    "LOCATION": "<LOCATION>",
    "IP_ADDRESS": "<IP>",
    "CREDIT_CARD": "<CARD>",
    "IBAN_CODE": "<IBAN>",
    "UK_NHS": "<ID>",
}
DEFAULT_MODEL = "en_core_web_lg"  # en_core_web_sm is faster but misses more names


class Anonymiser:
    def __init__(self, spacy_model: str = DEFAULT_MODEL, extra_terms: Iterable[str] = (), score_threshold: float = 0.35):
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine

        nlp = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": spacy_model}],
            }
        ).create_engine()
        self._analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
        self._anonymizer = AnonymizerEngine()
        self._threshold = score_threshold
        # Terms we already know are identifying (e.g. the user's own name and employer):
        # matched exactly, so they are removed even when the model doesn't spot them.
        self._extra = [t.strip() for t in extra_terms if t and len(t.strip()) > 2]

    def _operators(self):
        from presidio_anonymizer.entities import OperatorConfig

        return {name: OperatorConfig("replace", {"new_value": tag}) for name, tag in PLACEHOLDERS.items()}

    def anonymise(self, text: str) -> str:
        if not text:
            return text
        results = self._analyzer.analyze(
            text=text, language="en", entities=ENTITIES, score_threshold=self._threshold
        )
        # Known terms first, so a name we were told about can't survive a model miss.
        from presidio_analyzer import RecognizerResult

        lowered = text.lower()
        for term in self._extra:
            start = lowered.find(term.lower())
            while start != -1:
                results.append(RecognizerResult("PERSON", start, start + len(term), 1.0))
                start = lowered.find(term.lower(), start + len(term))
        return self._anonymizer.anonymize(text=text, analyzer_results=results, operators=self._operators()).text
