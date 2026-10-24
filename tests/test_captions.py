from udemy_transcripts.captions import Cue, parse_vtt, pick_caption


def vtt(*lines):
    return "\r\n".join(lines)   # los VTT de Udemy usan CRLF


def test_parses_times_and_joins_multiline_cues():
    cues = parse_vtt(vtt(
        "WEBVTT", "",
        "00:00:05.066 --> 00:00:08.866", "Hola a todos, bienvenidos", "a un nuevo vídeo.", "",
        "01:02:03.500 --> 01:02:04.000", "Segundo cue.", ""))
    assert cues == [Cue(5.066, 8.866, "Hola a todos, bienvenidos a un nuevo vídeo."),
                    Cue(3723.5, 3724.0, "Segundo cue.")]


def test_short_timestamps_without_hours():
    (cue,) = parse_vtt(vtt("WEBVTT", "", "04:15.250 --> 04:16.000", "texto"))
    assert (cue.start, cue.end) == (255.25, 256.0)


def test_numeric_cue_identifiers_are_dropped_but_numeric_sentences_kept():   # B4
    cues = parse_vtt(vtt(
        "WEBVTT", "",
        "1", "00:00:01.000 --> 00:00:02.000", "La respuesta es", "42", "",
        "2", "00:00:02.000 --> 00:00:03.000", "2024", ""))
    assert [c.text for c in cues] == ["La respuesta es 42", "2024"]


def test_non_numeric_identifiers_do_not_leak():   # B4
    cues = parse_vtt(vtt(
        "WEBVTT", "",
        "intro-1", "00:00:01.000 --> 00:00:02.000", "Hola", "",
        "cue-2", "00:00:02.000 --> 00:00:03.000", "Adiós", ""))
    assert [c.text for c in cues] == ["Hola", "Adiós"]


def test_ignores_header_note_style_and_region_blocks():
    cues = parse_vtt(vtt(
        "WEBVTT - título", "Kind: captions", "Language: es", "",
        "NOTE esto es un comentario", "de dos líneas", "",
        "STYLE", "::cue { color: red }", "",
        "REGION", "id:r1", "",
        "00:00:01.000 --> 00:00:02.000 align:start position:0%", "Hola", ""))
    assert [c.text for c in cues] == ["Hola"]


def test_strips_tags_and_unescapes_entities():
    (cue,) = parse_vtt(vtt("WEBVTT", "", "00:00:01.000 --> 00:00:02.000",
                           "<v Ana><c.loud>a &lt; b</c></v> &amp; &quot;c&quot;"))
    assert cue.text == 'a < b & "c"'


def test_collapses_rolling_duplicate_lines():
    cues = parse_vtt(vtt(
        "WEBVTT", "",
        "00:00:01.000 --> 00:00:02.000", "línea uno", "línea dos", "",
        "00:00:02.000 --> 00:00:03.000", "línea dos", "línea tres", ""))
    assert [c.text for c in cues] == ["línea uno línea dos", "línea tres"]


def test_cue_with_only_duplicates_or_empty_text_is_skipped():
    cues = parse_vtt(vtt(
        "WEBVTT", "",
        "00:00:01.000 --> 00:00:02.000", "igual", "",
        "00:00:02.000 --> 00:00:03.000", "igual", "",
        "00:00:03.000 --> 00:00:04.000", "<c></c>", ""))
    assert [c.text for c in cues] == ["igual"]


def test_handles_bom_lf_and_garbage():
    assert parse_vtt("﻿WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhola\n")[0].text == "hola"
    assert parse_vtt("") == []
    assert parse_vtt("WEBVTT\n\nxx --> yy\ntexto\n") == []


def caps(*specs):
    return [{"locale_id": loc, "source": src, "url": f"https://cdn/{loc}-{src}.vtt"}
            for loc, src in specs]


def test_pick_matches_language_prefix_with_region():
    cap, preferred = pick_caption(caps(("en_US", "manual"), ("es_LA", "manual")), ["es", "en"])
    assert (cap["locale_id"], preferred) == ("es_LA", True)


def test_pick_second_preference_is_flagged_not_preferred():   # B5
    cap, preferred = pick_caption(caps(("en_US", "manual")), ["es", "en"])
    assert (cap["locale_id"], preferred) == ("en_US", False)


def test_pick_falls_back_to_first_and_flags_it():   # B5
    cap, preferred = pick_caption(caps(("fr_FR", "manual"), ("de_DE", "manual")), ["es"])
    assert (cap["locale_id"], preferred) == ("fr_FR", False)


def test_pick_prefers_manual_over_auto_in_same_language():
    cap, _ = pick_caption(caps(("es_LA", "auto"), ("es_LA", "manual")), ["es"])
    assert cap["source"] == "manual"


def test_pick_exact_locale_and_no_false_prefix_match():
    cap, preferred = pick_caption(caps(("pt_BR", "manual"), ("es_ES", "manual")), ["es_ES", "pt"])
    assert (cap["locale_id"], preferred) == ("es_ES", True)
    cap, preferred = pick_caption(caps(("eng_XX", "manual")), ["en"])
    assert preferred is False


def test_pick_ignores_captions_without_url_and_handles_empty():
    assert pick_caption([], ["es"]) == (None, False)
    assert pick_caption(None, ["es"]) == (None, False)
    assert pick_caption([{"locale_id": "es_LA", "url": ""}], ["es"]) == (None, False)
    cap, _ = pick_caption([{"locale_id": "es_LA", "url": ""},
                           {"locale_id": "en_US", "url": "https://cdn/x.vtt"}], ["es", "en"])
    assert cap["locale_id"] == "en_US"


def test_pick_with_no_languages_takes_first_as_preferred():
    cap, preferred = pick_caption(caps(("fr_FR", "manual")), [])
    assert (cap["locale_id"], preferred) == ("fr_FR", True)
