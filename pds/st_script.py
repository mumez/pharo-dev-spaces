"""Render .st templates: `{{NAME}}` placeholders are replaced by Smalltalk literals."""

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent / "st"


def st_literal(value):
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return "#( " + " ".join(st_literal(each) for each in value) + " )"


def render_template(template, **values):
    for name, value in values.items():
        template = template.replace("{{" + name + "}}", st_literal(value))
    return template


def render_template_file(template_name, **values):
    return render_template((TEMPLATE_DIR / template_name).read_text(), **values)
