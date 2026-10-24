from udemy_transcripts.html2md import extract_images, html_to_markdown


def md(html, **kw):
    return html_to_markdown(html, **kw)


def test_paragraphs_and_inline_formatting():
    html = "<p>Hola <strong>mundo</strong> y <em>más</em> con <code>x = 1</code>.</p><p>Otro.</p>"
    assert md(html) == "Hola **mundo** y *más* con `x = 1`.\n\nOtro.\n"


def test_emphasis_never_keeps_inner_spaces_or_empty_marks():
    assert md("<p><strong>Hola </strong>mundo</p>") == "**Hola** mundo\n"
    assert md("<p>a<b> </b>b<i></i></p>") == "a b\n"
    assert md("<p><b>uno</b><b> dos</b></p>").count("**") == 4


def test_headings_shift_below_the_lesson_title():
    assert md("<h1>Título</h1><h2>Sub</h2><p>x</p>") == "## Título\n\n### Sub\n\nx\n"
    assert md("<h1>T</h1>", heading_shift=0) == "# T\n"
    assert md("<h6>Hondo</h6>") == "###### Hondo\n"


def test_links_and_images():
    assert md('<p>Mira <a href="https://x.dev/a?b=1">la doc</a>.</p>') == \
        "Mira [la doc](https://x.dev/a?b=1).\n"
    html = '<p><img src="https://cdn/a.png" alt="esquema"></p>'
    assert md(html) == "![esquema](https://cdn/a.png)\n"
    assert md(html, image_map={"https://cdn/a.png": "../recursos/s/l/img/a.png"}) == \
        "![esquema](../recursos/s/l/img/a.png)\n"


def test_unordered_ordered_and_nested_lists():
    html = "<ul><li>uno</li><li>dos<ul><li>dos.a</li></ul></li></ul><ol><li>x</li><li>y</li></ol>"
    assert md(html) == "- uno\n- dos\n  - dos.a\n\n1. x\n2. y\n"


def test_ordered_list_start_attribute():
    assert md('<ol start="3"><li>c</li><li>d</li></ol>') == "3. c\n4. d\n"


def test_code_blocks_keep_whitespace_and_language():
    html = '<pre class="prettyprint lang-java">int x = 1;\n  if (a &lt; b) {\n  }</pre>'
    assert md(html) == "```java\nint x = 1;\n  if (a < b) {\n  }\n```\n"
    html = '<pre><code class="language-xml">&lt;a/&gt;</code></pre>'
    assert md(html) == "```xml\n<a/>\n```\n"
    assert md("<pre>un ``` dentro</pre>").startswith("````\n")


def test_special_characters_in_text_are_escaped_but_not_in_code():
    assert md("<p>usa snake_case y 2 * 3 con &lt;div&gt;</p>") == \
        "usa snake\\_case y 2 \\* 3 con \\<div\\>\n"
    assert md("<p><code>a_b * c &lt;x&gt;</code></p>") == "`a_b * c <x>`\n"
    assert md("<p>1. no lista</p>") == "1\\. no lista\n"
    assert md("<p><code>un `tick`</code></p>") == "`un 'tick'`\n"


def test_blockquote_hr_and_br():
    assert md("<blockquote><p>cita</p></blockquote>") == "> cita\n"
    assert md("<p>a</p><hr><p>b</p>") == "a\n\n---\n\nb\n"
    assert md("<p>línea<br>otra</p>") == "línea  \notra\n"


def test_table():
    html = ("<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>x|y</td></tr>"
            "<tr><td>solo</td></tr></table>")
    assert md(html) == "| A | B |\n| --- | --- |\n| 1 | x\\|y |\n| solo |  |\n"


def test_source_line_breaks_are_not_hard_breaks_and_scripts_are_dropped():
    html = "<p>una\n   frase\n partida</p><script>alert(1)</script><style>p{}</style><p>fin</p>"
    assert md(html) == "una frase partida\n\nfin\n"


def test_text_outside_blocks_and_empty_input():
    assert md("texto suelto") == "texto suelto\n"
    assert md("") == "" and md(None) == "" and md("<p> </p>") == ""


def test_plain_mode_has_no_markdown_syntax():
    html = ('<h2>Título</h2><p>Hola <strong>mundo</strong> <a href="https://x.dev">aquí</a> '
            '<code>x</code></p><ul><li>uno</li></ul><pre>codigo()</pre>'
            '<p><img src="a.png" alt="esquema"></p>')
    assert md(html, plain=True) == (
        "Título\n\nHola mundo aquí (https://x.dev) x\n\n- uno\n\n    codigo()\n\n[imagen: esquema]\n")


def test_plain_link_with_same_text_is_not_repeated():
    assert md('<a href="https://x.dev">https://x.dev</a>', plain=True) == "https://x.dev\n"


def test_unclosed_and_malformed_html_does_not_crash():
    assert "uno" in md("<p>uno<ul><li>a<li>b</ul><b>negrita sin cerrar")
    assert md("<pre>sin cerrar") == "```\nsin cerrar\n```\n"


def test_extract_images_in_order_without_duplicates():
    html = ('<img src="https://c/a.png"><p><img alt="x" src="https://c/b.jpg"/>'
            "<img src='https://c/a.png'><img></p>")
    assert extract_images(html) == ["https://c/a.png", "https://c/b.jpg"]
    assert extract_images("") == [] and extract_images(None) == []


def test_emphasis_inside_code_or_headings_is_dropped():
    assert md("<p><strong>perfiles (<code><strong>dev</strong></code>, <code>prod</code>)</strong></p>") \
        == "**perfiles (`dev`, `prod`)**\n"
    assert md("<h3><strong>Resumen</strong> de <em>todo</em></h3>") == "#### Resumen de todo\n"
    assert md("<p><strong><code>x</code></strong></p>") == "**`x`**\n"
