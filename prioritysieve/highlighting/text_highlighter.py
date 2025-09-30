from __future__ import annotations

import re
from collections import deque

from .. import prioritysieve_globals
from ..prioritysieve_config import PrioritySieveConfig
from ..morpheme import Morpheme
from .ruby_classes import Ruby, TextRuby
from .status_class import Status

ruby_regex = re.compile(r" ?([^] \W]+)\[(.+?)\]")


class TextHighlighter:
    """
    Represents an expression to highlight. Tracks 2 sets of data, one for rubies the other
     for morph statuses. All the magic happens in _process() where we merge them together on top
     of the base string.
    """

    def __init__(
        self,
        am_config: PrioritySieveConfig,
        expression: str,
        morphemes: list[Morpheme],
        ruby_type: type[Ruby] = TextRuby,
    ):
        self.am_config: PrioritySieveConfig = am_config
        self._highlighted_expression: str | None = None
        self.expression: str = expression
        self.rubies: deque[Ruby] = deque()
        self.statuses: deque[Status] = deque()

        self._tag_rubies(ruby_type)
        self._tag_morphemes(self.expression.lower(), morphemes)

    def _tag_rubies(self, ruby_type: type[Ruby]) -> None:
        """
        Populate internal deque of found ruby locations.

        Anki ruby text has this format:
            "Text[Ruby]"
        where the base has to have a whitespace in front of it, or be the first word in the sentence.

        Correct: "世[よ]の 中[なか]"
        Incorrect: "世[よ]の中[なか]"

        This helps us determine the start of the ruby text even when the morphemizer incorrectly
         splits the word, which we can then use to override the start highlighting. However, when
         this occurs we can no longer use the morphemizer to infer the learning interval of the text
         so we have to give it the status prioritysieve_globals.STATUS_UNDEFINED.

        More info: https://docs.ankiweb.net/templates/fields.html?highlight=ruby#ruby-characters
        """

        end = 0

        while True:
            match = ruby_regex.search(self.expression, pos=end)

            if not match:
                break

            end = match.start() + len(match.group(1))

            self.rubies.append(
                ruby_type(match.start(), end, match.group(1), match.group(2))
            )
            self.expression = (
                self.expression[: match.start()]
                + match.group(1)
                + self.expression[match.end() :]
            )

    def _tag_morphemes(self, expression: str, morphemes: list[Morpheme]) -> None:
        """
        Populate internal deque of found morph locations.

        Start with the longest morphemes so that we do not tag parts of morphs, and then miss the
         bigger ones.

        Clear the found morph out of the string and replace it with spaces so that our indexes are
         correct for subsequent iterations.
        """

        for morph in sorted(
            morphemes, key=lambda morpheme: len(morpheme.inflection), reverse=True
        ):
            while True:
                start = expression.find(morph.inflection)

                if start == -1:
                    break

                end = start + len(morph.inflection)
                learning_status = morph.get_learning_status(
                    self.am_config.evaluate_morph_inflection,
                    self.am_config.interval_for_known_morphs,
                )

                self.statuses.append(
                    Status(start, end, learning_status, morph.inflection)
                )
                expression = (
                    expression[:start] + (" " * (end - start)) + expression[end:]
                )

        self.statuses = deque(sorted(self.statuses, key=lambda _range: _range.start))

    def highlighted(self) -> str:
        self._highlighted_expression = self.expression

        if self._highlighted_expression and (self.rubies or self.statuses):
            self._process()

        return self._highlighted_expression

    def _process(self) -> None:  # pylint:disable=too-many-branches, too-many-statements
        """
        Process the text in 'self._highlighted_expression', now that all the metadata has been
         gathered.

        This method works backwards through the sets of found morphs and rubies. It compares the
         relationship of the last morph and last ruby. Depending on the relationship, the base
         string is updated with relevant data from the morph and/or ruby. When one, the other, or
         both are processed, they are discarded and a new candidate for the discarded token is
         popped. The analysis then repeats until there are no tokens left.

        Scenarios Handled:

        1. No remaining statuses or rubies:
            Example: '(ㆆ _ ㆆ)?!'
            Action: Break
            Explanation: 'self._highlighted_expression' is fully handled.

        2. Only morphs remain (no more rubies):
            Example: '私...'
            Action: Wrap the current morph with the respective status.

        3. Only rubies remain (no more morphs):
            Example: `37[さんじゅうなな]！`
            Action: Wrap the current ruby (to the preceding whitespace) with the
             status prioritysieve_globals.STATUS_UNDEFINED.
             This undefined status is manufactured just-in-time. This turns all instances of this
             scenario into scenario 5.
            Explanation: We assume that rubies are intentionally curated into something that makes
             sense, so if there are no found morphs, that means the morphemizer is incorrect, and
             we cannot make any inferences about how well this section of text is known.

        4a. No overlap between status and ruby (ruby last):
            Example: '...です。 予定[よてい]'
            Action: Only wrap the later token in the string. If the ruby is later, we must
             manufacture an undefined status temporarily and use it.
            Explanation: The morph 'です' is checked against the ruby '予定[よてい]', but 'です' is
             independent of the ruby, i.e. no overlap, ruby is last, so we manufacture an undefined
             status to go with this ruby, and we annotate like scenario 5.

        4b. No overlap between status and ruby (morph last):
            Example: '予定[よてい]です'
            Action: Only wrap the later token in the string. If the morph is later, process it
             normally.
            Explanation: The morph 'です' is checked against the ruby '予定[よてい]', but 'です' is
             independent of the ruby, i.e. no overlap, morph is last, so it is wrapped with its
             respective status, and the ruby is left alone to be processed next time.

        5. Ruby and status match exactly:
            Example: '予定[よてい]'
            Action: Wrap the ruby with the respective status.

        6. Ruby is completely inside the status:
            Example: '相変[あいか]わらず'
            Action: Wrap everything with the respective status
            Explanation: The morph that has a corresponding status here is '相変わらず', i.e. the
             ruby is there to clarify the first part of the word.

        7. Status is completely inside the ruby:
            Example: '錬金術師[れんきんじゅつし]'
            Action: Wrap everything with the status prioritysieve_globals.STATUS_UNDEFINED
            Explanation: Occurs when multiple morphs match a single ruby. In this example the
             actual word is '錬金術師', but the morphemizer incorrectly splits it into
             ['錬金術', '師']. Since the morphemizer is incorrect, we cannot make an inference
             on how well the text is known.

        8. Ruby starts, then status starts, ruby ends, and status ends:
            Example: '謎解[なぞと]き'
            Action: Wrap everything with the status prioritysieve_globals.STATUS_UNDEFINED
            Explanation: This is a combination of scenarios 6 and 7.
             The correct word here is '謎解き' (scenario 6), but the morphemizer splits it into
             ['謎','解き'] (scenario 7).
        """

        ruby: Ruby | None = None
        status: Status | None = None

        while self._highlighted_expression is not None:

            if ruby is None and self.rubies:
                ruby = self.rubies.pop()

            if status is None and self.statuses:
                status = self.statuses.pop()

            # Scenario 1: Nothing more to be highlighted.
            if ruby is None and status is None:
                break

            # Scenario 2: There are only statuses.
            if ruby is None:
                # Ignore is here because (surprisingly) mypy can not tell the
                # only path that leads here requires status to be non-None.
                self._highlighted_expression = status.inject(self._highlighted_expression)  # type: ignore[union-attr]
                status = None
                continue

            # Scenario 3: There are only rubies.
            if status is None:
                # If there is no status for this ruby,
                # manufacture one and let Scenario 5 take over.
                status = Status(
                    ruby.start,
                    ruby.end,
                    prioritysieve_globals.STATUS_UNDEFINED,
                    self._highlighted_expression[ruby.start : ruby.end],
                )
                continue

            # Scenario 4: There is no overlap between ruby and status.
            if ruby.end <= status.start or ruby.start >= status.end:
                if ruby.start > status.start:
                    # There is no status for this ruby, manufacture one and update.
                    temp_status: Status = Status(
                        ruby.start,
                        ruby.end,
                        prioritysieve_globals.STATUS_UNDEFINED,
                        self._highlighted_expression[ruby.start : ruby.end],
                    )

                    # This is just like scenario 5.
                    self._highlighted_expression = (
                        self._highlighted_expression[: temp_status.start]
                        + temp_status.open()
                        + self._highlighted_expression[
                            temp_status.start : temp_status.start
                            + ruby.start
                            - temp_status.start
                        ]
                        + str(ruby)
                        + self._highlighted_expression[ruby.end : temp_status.end]
                        + temp_status.close()
                        + self._highlighted_expression[temp_status.end :]
                    )
                    ruby = None
                else:
                    self._highlighted_expression = status.inject(
                        self._highlighted_expression
                    )
                    status = None
                continue

            # Scenario 5: The status is the same as the ruby.
            # OR
            # Scenario 6: The ruby is completely inside the status.
            if ruby.start >= status.start and ruby.end <= status.end:
                self._highlighted_expression = (
                    self._highlighted_expression[: status.start]
                    + status.open()
                    + self._highlighted_expression[
                        status.start : status.start + ruby.start - status.start
                    ]
                    + str(ruby)
                    + self._highlighted_expression[ruby.end : status.end]
                    + status.close()
                    + self._highlighted_expression[status.end :]
                )

                # Pull and process rubies until the next ruby is outside of this status.
                while self.rubies:
                    if self.rubies[-1].end <= status.start:
                        break

                    ruby = self.rubies.pop()
                    ruby.start += status.open_len()
                    ruby.end += status.open_len()
                    self._highlighted_expression = ruby.inject(
                        self._highlighted_expression
                    )

                status = None
                ruby = None
                continue

            # Scenario 7: The status is completely inside the ruby.
            # OR
            # Scenario 8: The ruby starts then status starts, ruby ends, status ends."""
            if ruby.start <= status.start:
                status.status = prioritysieve_globals.STATUS_UNDEFINED
                self._highlighted_expression = (
                    self._highlighted_expression[: ruby.start]
                    + status.open()
                    + str(ruby)
                    + self._highlighted_expression[ruby.end : status.end]
                    + status.close()
                    + self._highlighted_expression[status.end :]
                )

                # Pull and process statuses until the next status is outside of this ruby.
                while self.statuses:
                    if self.statuses[-1].end <= ruby.start:
                        break
                    self.statuses.pop()

                ruby = None
                status = None
                continue

            # Just in case, to prevent infinite loop, we're disposing of the current pieces
            ruby = None
            status = None
