from pds.st_script import render_template, st_literal


def test_st_literal_quotes_strings_and_nests_arrays():
    assert st_literal("it's") == "'it''s'"
    assert st_literal(["a", ["b", "c"]]) == "#( 'a' #( 'b' 'c' ) )"


def test_render_template_substitutes_placeholders_with_literals():
    assert render_template("x := {{VALUE}}.", VALUE=["a"]) == "x := #( 'a' )."
