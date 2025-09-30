from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from aqt import mw

from . import prioritysieve_globals as am_globals
from .prioritysieve_db import PrioritySieveDB
from .exceptions import PriorityFileMalformedException, PriorityFileNotFoundException
from .reading_utils import normalize_reading
from .recalc.card_score import MORPH_UNKNOWN_PENALTY


class PriorityFileType:
    PriorityFile = "PriorityFile"
    StudyPlan = "StudyPlan"


class PriorityFileFormat:
    Minimal = "Minimal"
    Full = "Full"


class PriorityFile:

    def __init__(  # pylint:disable=too-many-arguments
        self,
        file_type: str,
        file_format: str,
        lemma_header_index: int,
        inflection_header_index: int | None = None,
        reading_header_index: int | None = None,
        lemma_priority_header_index: int | None = None,
        inflection_priority_header_index: int | None = None,
    ):
        self.type = file_type
        self.format = file_format
        self.lemma_header_index = lemma_header_index
        self.inflection_header_index = inflection_header_index
        self.reading_header_index = reading_header_index
        self.lemma_priority_header_index = lemma_priority_header_index
        self.inflection_priority_header_index = inflection_priority_header_index


def get_priority_files() -> list[str]:
    assert mw is not None
    path_generator = Path(
        mw.pm.profileFolder(), am_globals.PRIORITY_FILES_DIR_NAME
    ).glob("*.csv")
    priority_files = [file.name for file in path_generator if file.is_file()]
    return priority_files


def get_morph_priority(
    am_db: PrioritySieveDB,
    only_lemma_priorities: bool,
    morph_priority_selection: Iterable[str] | str,
) -> dict[tuple[str, str, str], int]:
    selections = _normalize_priority_selections(morph_priority_selection)

    merged_priorities: dict[tuple[str, str, str], int] = {}

    if am_globals.COLLECTION_FREQUENCY_OPTION in selections:
        collection_priorities = am_db.get_morph_priorities_from_collection(
            only_lemma_priorities=only_lemma_priorities
        )
        _merge_priorities(merged_priorities, collection_priorities)

    for selection in selections:
        if selection in (
            am_globals.COLLECTION_FREQUENCY_OPTION,
            am_globals.NONE_OPTION,
        ):
            continue

        file_priorities = _load_morph_priorities_from_file(
            priority_file_name=selection,
            only_lemma_priorities=only_lemma_priorities,
        )
        _merge_priorities(merged_priorities, file_priorities)

    return merged_priorities


def _normalize_priority_selections(
    morph_priority_selection: Iterable[str] | str,
) -> list[str]:
    if isinstance(morph_priority_selection, str):
        candidates = [morph_priority_selection]
    else:
        candidates = list(morph_priority_selection)

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        selection = candidate.strip()
        if not selection or selection == am_globals.NONE_OPTION:
            continue
        if selection in seen:
            continue
        seen.add(selection)
        normalized.append(selection)

    return normalized


def _load_morph_priorities_from_file(
    priority_file_name: str, only_lemma_priorities: bool
) -> dict[tuple[str, str, str], int]:
    assert mw is not None

    priority_file_path = Path(
        mw.pm.profileFolder(),
        am_globals.PRIORITY_FILES_DIR_NAME,
        priority_file_name,
    )
    try:
        with open(priority_file_path, encoding="utf-8") as csvfile:
            morph_reader = csv.reader(csvfile, delimiter=",")
            headers: list[str] | None = next(morph_reader, None)
            priority_file: PriorityFile = _get_file_type_and_format(
                priority_file_path, headers
            )
            return _get_morph_priorities_from_file(
                priority_file_path=priority_file_path,
                morph_reader=morph_reader,
                priority_file=priority_file,
                only_lemma_priorities=only_lemma_priorities,
            )
    except FileNotFoundError as exc:
        raise PriorityFileNotFoundException(str(priority_file_path)) from exc


def _get_morph_priorities_from_file(
    priority_file_path: Path,
    morph_reader: Any,
    priority_file: PriorityFile,
    only_lemma_priorities: bool,
) -> dict[tuple[str, str, str], int]:
    # Full-format priority files were designed to allow switching between evaluating
    # morphs based on their lemma or their inflections. However, this switching
    # is not possible with full-format study plans, so they must be treated differently.
    #
    # Scenarios to handle:
    #  - priority file minimal (only lemma) format
    #    - evaluating lemma -> ok
    #    - evaluating inflection -> raise exception
    #  - priority file full (lemma and inflection) format
    #    - evaluating lemma -> ok
    #    - evaluating inflection -> ok
    #  - study plan minimal (only lemma) format
    #    - evaluating lemma -> ok
    #    - evaluating inflection -> raise exception
    #  - study plan full (lemma and inflection) format
    #    - evaluating lemma -> raise exception
    #    - evaluating inflection -> ok

    morph_priority_dict: dict[tuple[str, str, str], int] = {}

    if only_lemma_priorities:
        if priority_file.format == PriorityFileFormat.Full:
            if priority_file.type == PriorityFileType.StudyPlan:
                raise PriorityFileMalformedException(
                    path=priority_file_path,
                    reason="Study plans containing inflections are incompatible with the 'evaluate lemmas' option.",
                )
            _populate_priorities_with_lemmas_from_full_priority_file(
                morph_reader=morph_reader,
                file_type_and_format=priority_file,
                morph_priority_dict=morph_priority_dict,
            )
            return morph_priority_dict

        # this could be either a study plan or priority file,
        # but both are handled the same
        _populate_priorities_with_lemmas_from_minimal_priority_file(
            morph_reader=morph_reader,
            file_type_and_format=priority_file,
            morph_priority_dict=morph_priority_dict,
        )
        return morph_priority_dict

    if priority_file.format == PriorityFileFormat.Minimal:
        raise PriorityFileMalformedException(
            path=priority_file_path,
            reason="Priority files or study plans without inflections are incompatible with the 'evaluate inflections' option.",
        )

    if priority_file.type == PriorityFileType.PriorityFile:
        _populate_priorities_with_lemmas_and_inflections_from_full_priority_file(
            morph_reader=morph_reader,
            file_type_and_format=priority_file,
            morph_priority_dict=morph_priority_dict,
        )
        return morph_priority_dict

    if priority_file.type == PriorityFileType.StudyPlan:
        _populate_priorities_with_lemmas_and_inflections_from_full_study_plan(
            morph_reader=morph_reader,
            file_type_and_format=priority_file,
            morph_priority_dict=morph_priority_dict,
        )
        return morph_priority_dict

    # this should never be reached
    raise PriorityFileMalformedException(
        path=priority_file_path, reason="unsupported priority file type or format"
    )


def _get_row_reading(row: list[str], priority_file: PriorityFile) -> str:
    index = priority_file.reading_header_index
    if index is None or index >= len(row):
        return ""
    return normalize_reading(row[index])


def _get_file_type_and_format(
    priority_file_path: Path, headers: list[str] | None
) -> PriorityFile:
    # Here is how to differentiate between the types and formats:
    #  - Minimal priority file/study plan: does __not__ have the am_globals.INFLECTION_HEADER
    #  - Full priority file: has the am_globals.INFLECTION_PRIORITY_HEADER
    #  - Full study plan: does __not__ have the am_globals.INFLECTION_PRIORITY_HEADER

    if headers is None or len(headers) == 0:
        raise PriorityFileMalformedException(
            path=str(priority_file_path),
            reason="Priority file does not have headers.",
        )

    if am_globals.LEMMA_HEADER not in headers:
        reason = f"Priority file is missing the '{am_globals.LEMMA_HEADER}' header"
        raise PriorityFileMalformedException(
            path=str(priority_file_path),
            reason=reason,
        )

    lemma_header_index: int = headers.index(am_globals.LEMMA_HEADER)
    reading_header_index: int | None = None

    if am_globals.READING_HEADER in headers:
        reading_header_index = headers.index(am_globals.READING_HEADER)

    if am_globals.INFLECTION_HEADER not in headers:
        # this is either a minimal priority file or a minimal study plan,
        # but we don't have to differentiate the file types since
        # minimal format files are handled in the same way
        return PriorityFile(
            file_type=PriorityFileType.PriorityFile,  # arbitrary choice
            file_format=PriorityFileFormat.Minimal,
            lemma_header_index=lemma_header_index,
            reading_header_index=reading_header_index,
        )

    inflection_header_index: int = headers.index(am_globals.INFLECTION_HEADER)

    if am_globals.LEMMA_PRIORITY_HEADER in headers:
        # full format priority file
        lemma_priority_header_index: int = headers.index(
            am_globals.LEMMA_PRIORITY_HEADER
        )
        try:
            # this should always exist at this point
            inflection_priority_header_index: int = headers.index(
                am_globals.INFLECTION_PRIORITY_HEADER
            )
        except ValueError as exc:
            reason = f"Priority file is missing the '{am_globals.INFLECTION_PRIORITY_HEADER}' header"
            raise PriorityFileMalformedException(
                path=str(priority_file_path),
                reason=reason,
            ) from exc

        return PriorityFile(
            file_type=PriorityFileType.PriorityFile,
            file_format=PriorityFileFormat.Full,
            lemma_header_index=lemma_header_index,
            inflection_header_index=inflection_header_index,
            reading_header_index=reading_header_index,
            lemma_priority_header_index=lemma_priority_header_index,
            inflection_priority_header_index=inflection_priority_header_index,
        )

    # here we should be left with a full format study plan
    return PriorityFile(
        file_type=PriorityFileType.StudyPlan,
        lemma_header_index=lemma_header_index,
        file_format=PriorityFileFormat.Full,
        inflection_header_index=inflection_header_index,
        reading_header_index=reading_header_index,
    )


def _populate_priorities_with_lemmas_and_inflections_from_full_priority_file(
    morph_reader: Any,
    file_type_and_format: PriorityFile,
    morph_priority_dict: dict[tuple[str, str, str], int],
) -> None:
    for index, row in enumerate(morph_reader):
        if index > MORPH_UNKNOWN_PENALTY:
            # rows after this will be ignored by the scoring algorithm
            break
        lemma = row[file_type_and_format.lemma_header_index]
        inflection = row[file_type_and_format.inflection_header_index]
        reading = _get_row_reading(row, file_type_and_format)
        key = (lemma, inflection, reading)
        priority = int(row[file_type_and_format.inflection_priority_header_index])
        _assign_priority_if_lower(morph_priority_dict, key, priority)


def _populate_priorities_with_lemmas_and_inflections_from_full_study_plan(
    morph_reader: Any,
    file_type_and_format: PriorityFile,
    morph_priority_dict: dict[tuple[str, str, str], int],
) -> None:
    for index, row in enumerate(morph_reader):
        if index > MORPH_UNKNOWN_PENALTY:
            # rows after this will be ignored by the scoring algorithm
            break
        lemma = row[file_type_and_format.lemma_header_index]
        inflection = row[file_type_and_format.inflection_header_index]
        reading = _get_row_reading(row, file_type_and_format)
        key = (lemma, inflection, reading)
        _assign_priority_if_lower(morph_priority_dict, key, index)


def _populate_priorities_with_lemmas_from_full_priority_file(
    morph_reader: Any,
    file_type_and_format: PriorityFile,
    morph_priority_dict: dict[tuple[str, str, str], int],
) -> None:
    for index, row in enumerate(morph_reader):
        if index > MORPH_UNKNOWN_PENALTY:
            # rows after this will be ignored by the scoring algorithm
            break
        lemma = row[file_type_and_format.lemma_header_index]
        reading = _get_row_reading(row, file_type_and_format)
        key = (lemma, lemma, reading)
        priority = int(row[file_type_and_format.lemma_priority_header_index])
        _assign_priority_if_lower(morph_priority_dict, key, priority)


def _populate_priorities_with_lemmas_from_minimal_priority_file(
    morph_reader: Any,
    file_type_and_format: PriorityFile,
    morph_priority_dict: dict[tuple[str, str, str], int],
) -> None:
    for index, row in enumerate(morph_reader):
        if index > MORPH_UNKNOWN_PENALTY:
            # rows after this will be ignored by the scoring algorithm
            break
        lemma = row[file_type_and_format.lemma_header_index]
        reading = _get_row_reading(row, file_type_and_format)
        key = (lemma, lemma, reading)
        _assign_priority_if_lower(morph_priority_dict, key, index)


def _merge_priorities(
    target: dict[tuple[str, str, str], int],
    source: dict[tuple[str, str, str], int],
) -> None:
    for key, priority in source.items():
        _assign_priority_if_lower(target, key, priority)


def _assign_priority_if_lower(
    priority_dict: dict[tuple[str, str, str], int],
    key: tuple[str, str, str],
    priority: int,
) -> None:
    existing = priority_dict.get(key)
    if existing is None or priority < existing:
        priority_dict[key] = priority
