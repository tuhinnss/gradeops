"""
Lightweight text utilities for OCR cleanup, question detection, marks parsing,
and validation. No extra ML dependencies — regex + heuristics only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.rubric import RubricItem

logger = logging.getLogger(__name__)

MIN_QUESTION_NUM = 1
MAX_QUESTION_NUM = 99
MAX_RUBRIC_QUESTIONS = 40
MAX_MARKS_PER_QUESTION = 50.0
MAX_EXAM_TOTAL_MARKS = 500.0
MIN_KEY_POINT_LEN = 8
MIN_ANSWER_CHARS = 10
MIN_OCR_FRAGMENT_CHARS = 15

QUESTION_LINE_RE = re.compile(
    r"^[\s\*]*"
    r"(?:"
    r"(?:Q(?:uestion)?\s*)(\d{1,2})\s*[\.\):\-]"
    r"|"
    r"(?:Question\s+)(\d{1,2})\s*[\.\):\-]"
    r"|"
    r"(\d{1,2})[\.\)]\s+(?=[A-Za-z\(\"\'])"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

EXAM_QUESTION_LINE_RE = re.compile(
    r"^[\s\*]*(\d{1,2})\.\s+"
    r"(?:Find|Obtain|Examine|Consider|Write|Solve|Prove|Show|Compute|Derive|Classify|Evaluate|Define|Draw|If|The|In|For|A\b)",
    re.IGNORECASE | re.MULTILINE,
)

MARKS_COMPOUND_RE = re.compile(
    r"\[\s*(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)?\s*\]",
    re.I,
)
MARKS_BRACKET_RE = re.compile(
    r"\[\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)?\s*\]",
    re.I,
)
MARKS_PATTERNS = [
    MARKS_COMPOUND_RE,
    MARKS_BRACKET_RE,
    re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)\s*\)", re.I),
    re.compile(r"(?:max(?:imum)?|total)?\s*marks?\s*[:\-]\s*(\d+(?:\.\d+)?)", re.I),
    re.compile(r"(?:worth|allocate[d]?)\s*(\d+(?:\.\d+)?)\s*marks?", re.I),
]

PAGE_FOOTER_RE = re.compile(r"^\s*\d{1,2}\s*$")
SOLUTION_SUBMARK_RE = re.compile(r"\.{3,}\s*\d+(?:\.\d+)?\s*marks?\s*$", re.I)
EXAM_TOTAL_RE = re.compile(
    r"(?:total|maximum)\s*marks?\s*[:\-]?\s*(\d+(?:\.\d+)?)",
    re.I,
)

NOISE_LINE_RE = re.compile(r"^[\s\W\d]{0,12}$")
SYMBOL_HEAVY_RE = re.compile(r"^[\W_]{3,}$")

SECTION_HEADER_RE = re.compile(
    r"Section\s+"
    r"(I{1,3}|IV|VI{0,3}|IX|X{1,3}|\d+)"
    r"\s*\(\s*(\d+)\s*questions?\s*of\s*(\d+(?:\.\d+)?)\s*Mark",
    re.IGNORECASE,
)

QUESTION_NUM_LINE_RE = re.compile(r"^\s*(\d{1,2})\.\s*$", re.MULTILINE)
QUESTION_INLINE_RE = re.compile(
    r"^\s*(\d{1,2})\.\s+(\S.+)$",
    re.MULTILINE,
)


@dataclass
class SectionMeta:
    section_id: str
    marks_per_question: float
    expected_count: int
    header_text: str


@dataclass
class ParsedQuestionBlock:
    question_number: str
    body: str
    max_marks: float
    line_index: int
    section_label: str = ""
    local_number: int = 0


def clean_ocr_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x0c", " ").replace("\ufeff", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    lines_out: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            lines_out.append("")
            continue
        line = re.sub(r"\s+", " ", line)
        if NOISE_LINE_RE.match(line) or SYMBOL_HEAVY_RE.match(line):
            continue
        alnum = sum(1 for c in line if c.isalnum())
        if alnum < 2 and len(line) < MIN_OCR_FRAGMENT_CHARS:
            continue
        lines_out.append(line)
    cleaned = "\n".join(lines_out)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def normalize_question_label(num: int | str) -> str:
    try:
        n = int(str(num).strip())
    except (ValueError, TypeError):
        return ""
    if not (MIN_QUESTION_NUM <= n <= MAX_QUESTION_NUM):
        return ""
    return f"Q{n}"


def is_valid_question_number(num: int | str) -> bool:
    try:
        n = int(str(num).strip())
    except (ValueError, TypeError):
        return False
    return MIN_QUESTION_NUM <= n <= MAX_QUESTION_NUM


def extract_marks_from_block(text: str, *, prefer_first: bool = True) -> float:
    header = "\n".join(text.splitlines()[:12])[:1200]
    compound = MARKS_COMPOUND_RE.search(header)
    if compound:
        total = float(compound.group(1)) + float(compound.group(2))
        if 0.5 <= total <= MAX_MARKS_PER_QUESTION:
            return total
    bracket_vals: list[float] = []
    for m in MARKS_BRACKET_RE.finditer(header):
        val = float(m.group(1))
        if 0.5 <= val <= MAX_MARKS_PER_QUESTION:
            bracket_vals.append(val)
    if bracket_vals:
        return bracket_vals[0]
    candidates: list[float] = []
    for pat in MARKS_PATTERNS[2:]:
        for m in pat.finditer(header):
            try:
                val = float(m.group(1))
            except (ValueError, IndexError):
                continue
            if 0.5 <= val <= MAX_MARKS_PER_QUESTION:
                candidates.append(val)
    return candidates[0] if candidates else 0.0


def parse_declared_exam_total(text: str) -> float | None:
    m = EXAM_TOTAL_RE.search(text[:2500])
    return float(m.group(1)) if m else None


def is_noise_fragment(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) < MIN_OCR_FRAGMENT_CHARS:
        return True
    alnum = sum(1 for c in cleaned if c.isalnum())
    if alnum < 4:
        return True
    if alnum / max(len(cleaned), 1) < 0.25:
        return True
    return False


def keyword_overlap_score(answer: str, reference: str) -> float:
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "and", "or", "to", "of",
        "in", "for", "on", "with", "as", "by", "at", "it", "this", "that",
    }

    def tokens(s: str) -> set[str]:
        return {
            w.lower()
            for w in re.findall(r"[a-zA-Z]{3,}", s)
            if w.lower() not in stop
        }

    ta, tr = tokens(answer), tokens(reference)
    if not tr or not ta:
        return 0.0
    return len(ta & tr) / len(tr)


def has_section_structure(text: str) -> bool:
    return len(SECTION_HEADER_RE.findall(text)) >= 1 and bool(
        re.search(r"Section\s+II", text, re.I)
    )


def parse_section_metas(text: str) -> list[tuple[int, SectionMeta]]:
    metas: list[tuple[int, SectionMeta]] = []
    for m in SECTION_HEADER_RE.finditer(text):
        metas.append(
            (
                m.start(),
                SectionMeta(
                    section_id=m.group(1).strip().upper(),
                    expected_count=int(m.group(2)),
                    marks_per_question=float(m.group(3)),
                    header_text=m.group(0),
                ),
            )
        )
    return metas


def _is_page_footer_line(line: str) -> bool:
    s = line.strip()
    if PAGE_FOOTER_RE.match(s):
        return True
    if re.match(r"^\d{1,2}$", s):
        return True
    return False


def _extract_questions_from_section_body(
    body: str,
    section: SectionMeta,
    char_offset: int,
) -> list[tuple[int, int, str]]:
    lines = body.splitlines()
    found: list[tuple[int, int, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or _is_page_footer_line(line):
            i += 1
            continue
        if SECTION_HEADER_RE.search(line) or re.match(r"^Section\s+", line, re.I):
            break

        local_num: int | None = None
        content_start = i
        parts: list[str] = []

        m_inline = QUESTION_INLINE_RE.match(line)
        if m_inline:
            local_num = int(m_inline.group(1))
            parts = [m_inline.group(2).strip()]
            i += 1
        elif QUESTION_NUM_LINE_RE.match(line):
            local_num = int(QUESTION_NUM_LINE_RE.match(line).group(1))  # type: ignore[union-attr]
            i += 1
        else:
            i += 1
            continue

        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                continue
            if _is_page_footer_line(nxt):
                i += 1
                continue
            if (
                QUESTION_NUM_LINE_RE.match(nxt)
                or QUESTION_INLINE_RE.match(nxt)
                or SECTION_HEADER_RE.search(nxt)
                or re.match(r"^Section\s+", nxt, re.I)
            ):
                break
            parts.append(nxt)
            i += 1

        body_text = " ".join(parts).strip()
        if local_num and len(body_text) >= 3:
            found.append((local_num, char_offset + content_start, body_text))

    by_local: dict[int, tuple[int, str]] = {}
    for local_num, pos, content in found:
        if local_num not in by_local or len(content) > len(by_local[local_num][1]):
            by_local[local_num] = (pos, content)
    return [
        (local_num, pos, content)
        for local_num, (pos, content) in sorted(by_local.items())
    ]


def find_section_aware_question_blocks(text: str) -> list[ParsedQuestionBlock]:
    text = clean_ocr_text(text)
    section_metas = parse_section_metas(text)
    if not section_metas:
        return []

    blocks: list[ParsedQuestionBlock] = []
    global_index = 0

    for idx, (start, meta) in enumerate(section_metas):
        end = section_metas[idx + 1][0] if idx + 1 < len(section_metas) else len(text)
        section_body = text[start:end]
        questions = _extract_questions_from_section_body(section_body, meta, start)

        logger.info(
            "Section %s: expected %d @ %.1f mark(s) each — detected %d",
            meta.section_id,
            meta.expected_count,
            meta.marks_per_question,
            len(questions),
        )

        detected_locals: set[int] = set()
        for local_num, line_pos, q_body in questions:
            global_index += 1
            detected_locals.add(local_num)
            blocks.append(
                ParsedQuestionBlock(
                    question_number=f"Q{global_index}",
                    body=q_body,
                    max_marks=meta.marks_per_question,
                    line_index=line_pos,
                    section_label=f"Section {meta.section_id}",
                    local_number=local_num,
                )
            )

        for local_num in range(1, meta.expected_count + 1):
            if local_num in detected_locals:
                continue
            global_index += 1
            logger.warning(
                "Section %s: synthesizing Q local %d (not found in text)",
                meta.section_id,
                local_num,
            )
            blocks.append(
                ParsedQuestionBlock(
                    question_number=f"Q{global_index}",
                    body=f"Section {meta.section_id} question {local_num}",
                    max_marks=meta.marks_per_question,
                    line_index=start,
                    section_label=f"Section {meta.section_id}",
                    local_number=local_num,
                )
            )

    total = sum(b.max_marks for b in blocks)
    logger.info(
        "Section-aware parse: %d questions, total marks %.1f",
        len(blocks),
        total,
    )
    return blocks


def _collect_question_matches(text: str) -> list[tuple[int, str, int]]:
    found: list[tuple[int, str, int]] = []
    seen_positions: set[int] = set()

    def add_match(m: re.Match, num_group: int) -> None:
        num_str = m.group(num_group)
        if not num_str:
            return
        label = normalize_question_label(num_str)
        if not label:
            return
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.start())
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end].strip()
        if PAGE_FOOTER_RE.match(line):
            return
        pos_key = m.start() // 10
        if pos_key in seen_positions:
            return
        seen_positions.add(pos_key)
        found.append((m.start(), label, m.end()))

    for m in QUESTION_LINE_RE.finditer(text):
        num_str = m.group(1) or m.group(2) or m.group(3)
        if num_str:
            add_match(m, 1 if m.group(1) else (2 if m.group(2) else 3))
    for m in EXAM_QUESTION_LINE_RE.finditer(text):
        add_match(m, 1)

    earliest: dict[str, tuple[int, str, int]] = {}
    for start, label, end in sorted(found, key=lambda x: x[0]):
        if label not in earliest:
            earliest[label] = (start, label, end)
    return sorted(earliest.values(), key=lambda x: x[0])


def find_question_blocks(text: str) -> list[ParsedQuestionBlock]:
    text = clean_ocr_text(text)
    if not text:
        return []
    if has_section_structure(text):
        section_blocks = find_section_aware_question_blocks(text)
        if section_blocks:
            return section_blocks
    matches = _collect_question_matches(text)
    if not matches:
        return []
    blocks: list[ParsedQuestionBlock] = []
    for i, (start, label, end_pos) in enumerate(matches):
        block_end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        body = text[end_pos:block_end].strip()
        header_window = text[start : min(block_end, start + 900)]
        marks = extract_marks_from_block(header_window)
        blocks.append(
            ParsedQuestionBlock(
                question_number=label,
                body=body,
                max_marks=marks,
                line_index=start,
            )
        )
    return blocks


def extract_bullet_key_points(body: str) -> list[str]:
    points: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if len(line) < MIN_KEY_POINT_LEN or SOLUTION_SUBMARK_RE.search(line):
            continue
        m = re.match(r"^[\-\*•]\s+(.+)$", line)
        if m:
            points.append(m.group(1).strip())
            continue
        m = re.match(r"^[a-zA-Z][\.\)]\s+(.+)$", line)
        if m and len(m.group(1)) >= MIN_KEY_POINT_LEN:
            points.append(m.group(1).strip())
    unique: list[str] = []
    for p in points:
        if not any(keyword_overlap_score(p, u) > 0.85 for u in unique):
            unique.append(p)
    return unique[:15]


def extract_rubric_key_points(body: str) -> list[str]:
    points = extract_bullet_key_points(body)
    if points:
        return points
    scheme_match = re.search(
        r"marking\s*scheme\s*:?\s*(.+?)(?=\n\n|\Z)",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    if scheme_match:
        for line in scheme_match.group(1).splitlines():
            line = line.strip()
            if len(line) >= MIN_KEY_POINT_LEN and not SOLUTION_SUBMARK_RE.search(line):
                points.append(line[:300])
    if not points:
        stem = body.split("Solution:")[0].split("solution:")[0]
        for line in stem.splitlines():
            line = line.strip()
            if (
                len(line) >= 12
                and not line.lower().startswith("solution")
                and not MARKS_BRACKET_RE.search(line)
            ):
                points.append(line[:400])
                break
    if not points and len(body.strip()) >= 8:
        points.append(body.strip()[:400])
    unique: list[str] = []
    for p in points:
        if not any(keyword_overlap_score(p, u) > 0.85 for u in unique):
            unique.append(p)
    return unique[:12]


def validate_rubric_items(items: list[RubricItem]) -> list[RubricItem]:
    from app.schemas.rubric import RubricItem

    if not items:
        return []
    by_q: dict[str, RubricItem] = {}
    for item in items:
        label = normalize_question_label(
            item.question_number.replace("Q", "").replace("q", "")
        )
        if not label:
            continue
        marks = float(item.max_marks or 0)
        if marks <= 0 or marks > MAX_MARKS_PER_QUESTION:
            marks = extract_marks_from_block(" ".join(item.key_points)) or 0.0
        if marks <= 0 and item.key_points:
            marks = min(float(len(item.key_points)), MAX_MARKS_PER_QUESTION)
        key_points = [
            kp.strip()
            for kp in item.key_points
            if kp and len(kp.strip()) >= MIN_KEY_POINT_LEN and not is_noise_fragment(kp)
        ]
        cleaned = RubricItem(
            question_number=label,
            max_marks=min(marks, MAX_MARKS_PER_QUESTION),
            key_points=key_points,
            negative_conditions=item.negative_conditions[:8],
            partial_credit_rules=item.partial_credit_rules[:8],
        )
        if label not in by_q:
            by_q[label] = cleaned
        else:
            score_new = len(cleaned.key_points) * 2 + cleaned.max_marks
            score_old = len(by_q[label].key_points) * 2 + by_q[label].max_marks
            if score_new > score_old:
                by_q[label] = cleaned
    result = sorted(
        by_q.values(),
        key=lambda x: int(x.question_number.replace("Q", "")),
    )
    if len(result) > MAX_RUBRIC_QUESTIONS:
        result = result[:MAX_RUBRIC_QUESTIONS]
    total = sum(i.max_marks for i in result)
    logger.info(
        "Validated rubric: %d questions, total marks %.1f — %s",
        len(result),
        total,
        ", ".join(f"{i.question_number}={i.max_marks}" for i in result),
    )
    return result


def repair_missing_questions(
    items: list[RubricItem],
    blocks: list[ParsedQuestionBlock],
    declared_total: float | None,
) -> list[RubricItem]:
    from app.schemas.rubric import RubricItem

    by_q = {i.question_number: i for i in items}
    for block in blocks:
        if block.question_number not in by_q and block.max_marks > 0:
            by_q[block.question_number] = RubricItem(
                question_number=block.question_number,
                max_marks=block.max_marks,
                key_points=extract_rubric_key_points(block.body),
            )
    result = sorted(
        by_q.values(),
        key=lambda x: int(x.question_number.replace("Q", "")),
    )
    parsed_total = sum(i.max_marks for i in result)
    if declared_total and parsed_total < declared_total * 0.9:
        logger.warning(
            "Parsed total %.1f < declared %.1f",
            parsed_total,
            declared_total,
        )
    return result


def rubric_total_marks(items: list[RubricItem]) -> float:
    return round(sum(i.max_marks for i in items), 2)


def merge_answers_by_question(
    answers: list[dict],
    rubric_questions: list[str] | None = None,
) -> list[dict]:
    rubric_set: set[str] | None = None
    if rubric_questions:
        rubric_set = {
            normalize_question_label(q.replace("Q", ""))
            for q in rubric_questions
        }
        rubric_set.discard("")
    buckets: dict[str, list[dict]] = {}
    for ans in answers:
        raw_q = ans.get("question_number", "")
        label = normalize_question_label(str(raw_q).lstrip("Qq") or raw_q)
        if not label:
            continue
        if rubric_set is not None and label not in rubric_set:
            continue
        text = clean_ocr_text(ans.get("extracted_text", "") or "")
        if is_noise_fragment(text) and ans.get("is_blank", True):
            continue
        entry = {**ans, "question_number": label, "extracted_text": text}
        buckets.setdefault(label, []).append(entry)
    merged: list[dict] = []
    for label, group in sorted(
        buckets.items(),
        key=lambda x: int(x[0].replace("Q", "")) if x[0][1:].isdigit() else 999,
    ):
        best = max(
            group,
            key=lambda a: (len(a.get("extracted_text", "")), a.get("ocr_confidence", 0)),
        )
        text = best.get("extracted_text", "")
        best["is_blank"] = len(re.sub(r"\s+", "", text)) < MIN_ANSWER_CHARS
        merged.append(best)
    return merged


def round_marks(value: float, step: float = 0.5) -> float:
    return round(round(value / step) * step, 2)


def adjust_ocr_confidence(base: float, text: str) -> float:
    if not text or is_noise_fragment(text):
        return min(base, 0.25)
    score = base
    alnum = sum(1 for c in text if c.isalnum())
    ratio = alnum / max(len(text), 1)
    if ratio > 0.5:
        score += 0.1
    if len(text) > 40:
        score += 0.05
    if len(re.findall(r"[a-zA-Z]{2,}", text)) >= 5:
        score += 0.05
    return min(0.98, max(0.15, score))


def log_rubric_parse_debug(
    source: str,
    text_preview: str,
    blocks: list[ParsedQuestionBlock],
    items: list,
    declared_total: float | None,
) -> None:
    logger.info("=== RUBRIC PARSE DEBUG (%s) ===", source)
    logger.info("Text preview: %s", text_preview[:500].replace("\n", " "))
    logger.info("Declared exam total: %s", declared_total)
    logger.info("Detected question count: %d", len(blocks))
    for b in blocks:
        sec = f" | {b.section_label} local#{b.local_number}" if b.section_label else ""
        logger.info(
            "  %s%s | marks=%.1f | %s",
            b.question_number,
            sec,
            b.max_marks,
            b.body[:100].replace("\n", " "),
        )
    final_total = sum(i.max_marks for i in items)
    logger.info(
        "Final rubric: %d questions, total=%.1f — %s",
        len(items),
        final_total,
        ", ".join(f"{i.question_number}={i.max_marks}" for i in items),
    )
    logger.info("=== END RUBRIC PARSE DEBUG ===")
