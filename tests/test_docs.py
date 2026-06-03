from bxengine.docs import build_signature_from_docstring, get_docs
from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension, bpp_function
from bxengine.runtime.extensions.builtin import BuiltinExtension


class CategorizedExtension(BxeStatelessExtension):
    @bpp_function(name="PRIMARY", aliases=("ALIAS",), category="Explicit Category")
    def primary(self, value):
        """Does a documented thing.
        @parameter value the value to use
        @returns the result"""
        return value

    @bpp_function()
    def TAGGED(self):
        """Uses a docstring category.
        @category Tagged Category"""
        return ""


def test_get_docs_keeps_categories_and_alias_relationships():
    docs = get_docs(CategorizedExtension)

    primary = docs["PRIMARY"]
    alias = docs["ALIAS"]
    tagged = docs["TAGGED"]

    assert primary.category == "Explicit Category"
    assert primary.aliases == ("ALIAS",)
    assert not primary.is_alias
    assert alias.category == "Explicit Category"
    assert alias.is_alias
    assert alias.alias_of == "PRIMARY"
    assert "`ALIAS` is an alias for `PRIMARY`" in (alias.documentation_markdown or "")
    assert tagged.category == "Tagged Category"


def test_signature_builder_uses_docstring_parameters():
    docstring = """Example function.
    @parameter a first value
    continued description
    @optional b second value
    """

    assert build_signature_from_docstring("EXAMPLE", docstring) == "[EXAMPLE a b?]"
