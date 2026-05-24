from bxengine.runtime.extensions import BxeExtensionBase

def get_docs(ext: type[BxeExtensionBase]) -> dict[str, str]:
    ext_docs = {}
    for attr_name in dir(ext):
        if attr_name.startswith("_"):
            continue
        attr = getattr(ext, attr_name, None)
        if attr is None:
            continue
        if callable(attr) and getattr(attr, "_is_bpp_function", False):
            ext_docs[attr_name] = attr.__doc__
    return ext_docs
