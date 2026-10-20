"""Resumo extrativo local: escolhe as frases que melhor representam o texto, sem chamar serviço externo.

É o provedor padrão para a plataforma funcionar sem chave de API. A pontuação combina frequência dos termos
(com peso extra para palavras do título e dos títulos de seção), posição no texto e corte de redundância.
"""

import math
import re
import unicodedata
from collections import Counter

STOPWORDS_PT = set(
    """
a à às ao aos as o os um uma uns umas de da das do dos dum duma em na nas no nos num numa por pela pelas pelo pelos
para pra com sem sob sobre entre até após ante contra desde e ou mas nem que se como quando onde porque porquê pois
já também só ainda muito muita muitos muitas pouco pouca mais menos tão tanto tanta todo toda todos todas cada outro
outra outros outras mesmo mesma mesmos mesmas este esta estes estas esse essa esses essas aquele aquela aqueles
aquelas isto isso aquilo eu tu ele ela nós vós eles elas me te lhe nos vos lhes meu minha meus minhas seu sua seus
suas nosso nossa nossos nossas ser é são era eram foi foram será serão seja sejam sendo sido estar está estão estava
estavam esteve estiveram ter tem têm tinha tinham teve tiveram terá haver há havia houve fazer faz fazem feito pode
podem poderá deve devem deverá vai vão ir sim não qual quais quem cujo cuja cujos cujas lá aqui ali aí então assim
bem cada vez vezes ano anos dia dias forma parte caso tipo além apenas sempre nunca agora antes depois durante
você vocês pode podem poder fazer isso aqui tudo nada algo alguns algumas qualquer coisa coisas meses mês semana
hora horas primeiro primeira segundo segunda exemplo exemplos sobre outro null true false item itens página páginas
""".split()
)
STOPWORDS_EN = set(
    """
the a an and or but of to in on at by for with from as is are was were be been being it its this that these those
which who whom what when where why how not no yes can could should would may might must will shall do does did
done have has had having into over under than then there their they them he she his her we our you your i me my
also only just more most such other some any each all both few many much very own same so too out up down about
""".split()
)
STOPWORDS_ES = set("el la los las un una unos unas del al y o pero que en por para con sin es son fue ser está".split())

ABBREVIATIONS = {"sr", "sra", "dr", "dra", "prof", "profa", "p", "pág", "págs", "ex", "etc", "art", "fig", "cap",
                 "vol", "nº", "n", "obs", "ltda", "s.a", "av", "e.g", "i.e", "mr", "mrs", "no"}

WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9'-]*")
SENTENCE_END = re.compile(r"(?<=[.!?…])[\"”’)\]]*\s+(?=[\"“‘(\[]?[A-ZÀ-Ý0-9])")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def guess_language(text: str) -> str:
    sample = words(text[:20000])
    if not sample:
        return ""
    scores = {
        "pt": sum(w in STOPWORDS_PT for w in sample),
        "en": sum(w in STOPWORDS_EN for w in sample),
        "es": sum(w in STOPWORDS_ES for w in sample),
    }
    lang, score = max(scores.items(), key=lambda item: item[1])
    return lang if score >= max(5, len(sample) * 0.08) else ""


def _norm(line: str) -> str:
    return re.sub(r"[\d\s]+", "", line).lower()


def _flush(current: list[str], paragraphs: list[str]) -> None:
    if current:
        paragraphs.append(" ".join(current))
        current.clear()


def clean_text(text: str, one_paragraph_per_line: bool = False) -> list[str]:
    """Devolve os parágrafos de texto corrido: junta linhas quebradas, desfaz hifenização e descarta capa,
    cabeçalhos e rodapés repetidos (mesmo com o número da página mudando) e títulos de seção."""
    pages = text.split("\f") if "\f" in text else [text]
    seen = Counter()
    for page in pages:
        for key in {_norm(ln) for ln in page.splitlines() if ln.strip()}:
            seen[key] += 1
    repeated = {key for key, n in seen.items() if key and len(pages) >= 3 and n >= max(2, len(pages) * 0.3)}

    paragraphs: list[str] = []
    for index, page in enumerate(pages):
        lines = [ln.strip() for ln in page.splitlines()]
        if index == 0 and len(pages) > 2 and len(words(page)) < 80:
            continue  # capa
        lengths = sorted(len(ln) for ln in lines if len(ln) > 20)
        median = lengths[len(lengths) // 2] if lengths else 80
        current: list[str] = []
        for line in lines:
            if not line or _norm(line) in repeated or re.fullmatch(r"[\d\s.\-–—|/·•]+", line):
                _flush(current, paragraphs)
                continue
            ends_sentence = line[-1] in ".!?…:;\"”)"
            heading = not ends_sentence and not line.endswith("-") and (
                len(line) < 0.65 * median or (one_paragraph_per_line and len(line) < 90)
            )
            if heading:
                _flush(current, paragraphs)
                continue
            if current and current[-1].endswith("-") and line[:1].islower():
                current[-1] = current[-1][:-1] + line
            else:
                current.append(line)
            if one_paragraph_per_line:
                _flush(current, paragraphs)
        _flush(current, paragraphs)
    return [re.sub(r"\s+", " ", p).strip() for p in paragraphs if p.strip()]


def split_sentences(paragraph: str) -> list[str]:
    parts = SENTENCE_END.split(paragraph)
    sentences: list[str] = []
    for part in parts:
        if sentences:
            last_word = sentences[-1].rstrip(".").rsplit(" ", 1)[-1].lower()
            if last_word in ABBREVIATIONS or (len(last_word) == 1 and last_word.isalpha()):
                sentences[-1] = f"{sentences[-1]} {part}"
                continue
        sentences.append(part.strip())
    return [s for s in sentences if s]


CODE_RE = re.compile(r"[=_{}<>\\]|\(\)|\b[A-Z]{3,}\b.*\b[A-Z]{3,}\b")


def is_candidate(sentence: str) -> bool:
    if not 40 <= len(sentence) <= 320:
        return False
    if not re.search(r"[.!?…][\"”’)]*$", sentence) or sentence.count("|") > 1 or CODE_RE.search(sentence):
        return False
    letters = sum(c.isalpha() for c in sentence)
    if letters / len(sentence) < 0.7:
        return False
    return sentence[0].isupper() or sentence[0] in "“\"(" or sentence[0].isdigit()


def keywords(
    text: str, title: str = "", headings: list[str] | None = None, limit: int = 4, author: str = "", by_line: bool = False
) -> list[str]:
    stop = STOPWORDS_PT | STOPWORDS_EN | STOPWORDS_ES | set(words(author))
    body = "\n".join(clean_text(text[:300000], by_line)) or text[:300000]
    sequence = words(body)
    useful = [len(w) > 3 and w not in stop and not any(c.isdigit() for c in w) for w in sequence]
    counts = Counter(w for w, ok in zip(sequence, useful) if ok)
    if not counts:
        return []
    for w in words(title):
        if w in counts:
            counts[w] += 3
    for heading in headings or []:
        for w in words(heading):
            if w in counts:
                counts[w] += 1
    bigrams = Counter(
        (a, b) for (a, ok_a), (b, ok_b) in zip(zip(sequence, useful), zip(sequence[1:], useful[1:])) if ok_a and ok_b
    )
    picked: list[str] = []
    for (a, b), n in bigrams.most_common(20):
        if n >= 3 and a != b and len(picked) < 2:
            picked.append(f"{a} {b}")
    used = {strip_accents(w) for p in picked for w in p.split()}
    for w, _ in counts.most_common(60):
        if len(picked) >= limit:
            break
        key = strip_accents(w)
        if key not in used and not any(key[:5] == u[:5] for u in used):
            picked.append(w)
            used.add(key)
    return picked[:limit]


def summarize(
    text: str, title: str = "", headings: list[str] | None = None, max_chars: int = 320, by_line: bool = False
) -> str:
    paragraphs = clean_text(text, by_line)
    sentences: list[tuple[int, str]] = []
    for paragraph in paragraphs:
        for sentence in split_sentences(paragraph):
            if is_candidate(sentence):
                sentences.append((len(sentences), sentence))
    if not sentences:
        flat = " ".join(paragraphs)[:max_chars]
        return shorten(flat, max_chars) if flat else ""

    stop = STOPWORDS_PT | STOPWORDS_EN | STOPWORDS_ES
    doc_words = [w for _, s in sentences for w in words(s) if w not in stop and len(w) > 2]
    freq = Counter(doc_words)
    top = freq.most_common(1)[0][1] if freq else 1
    boost = {w for w in words(title) if w not in stop} | {
        w for h in headings or [] for w in words(h) if w not in stop
    }

    total = len(sentences)
    scored = []
    for index, sentence in sentences:
        terms = {w for w in words(sentence) if w not in stop and len(w) > 2}
        if not terms:
            continue
        weight = sum(freq[w] / top + (0.6 if w in boost else 0) for w in terms) / math.sqrt(len(terms))
        position = 2.0 if index == 0 else 1.0 + 0.6 * max(0.0, 1 - index / max(total * 0.25, 1))
        scored.append((weight * position, index, sentence, terms))
    scored.sort(reverse=True)

    chosen: list[tuple[int, str, set]] = []
    length = 0
    for _, index, sentence, terms in scored:
        if any(len(terms & other) / max(len(terms | other), 1) > 0.45 for _, _, other in chosen):
            continue
        if length + len(sentence) + 1 > max_chars and chosen:
            continue
        chosen.append((index, sentence, terms))
        length += len(sentence) + 1
        if length > max_chars * 0.7 or len(chosen) >= 3:
            break
    chosen.sort()
    return shorten(" ".join(s for _, s, _ in chosen), max_chars + 40)


def shorten(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"
