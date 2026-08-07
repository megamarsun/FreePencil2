bl_info = {
    "name": "FreePencil",
    "author": "Masamune Sakaki",
    "version": (2, 6, 0),
    # インストール可能な下限。blender_manifest.toml の blender_version_min と
    # 同じ値にすること(テスト t32 が一致を固定している)。
    # 4.2 は限定対応 = レンダリングは動くがライブプレビューは出ない。
    # プレビューの下限は compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR(4.3)。
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > FreePencil",
    "description": "FreePencil: Vertex Colors and Node Generation Tools",
    "warning": "",
    "category": "Object",
}
# バージョンだけ個別変数にする
ADDON_VERSION = bl_info["version"]

import bpy
import typing
import inspect
import pkgutil
import importlib
import logging
import gettext
import io
import subprocess
from pathlib import Path

__all__ = (
    "init",
    "register",
    "unregister",
)

# Blender のバージョン情報
blender_version = bpy.app.version

# グローバル変数（サブモジュール一覧と登録すべきクラスの順序）
modules = None
ordered_classes = None
# Translation dictionary loaded at runtime
translation_dict = None

logger = logging.getLogger(__name__)


class Utf8GNUTranslations(gettext.GNUTranslations):
    """GNUTranslations that falls back to UTF-8 when no charset is given."""

    def _parse(self, fp):  # type: ignore[override]
        try:
            super()._parse(fp)
        except UnicodeDecodeError:
            fp.seek(0)
            self._charset = "utf-8"
            gettext.GNUTranslations._parse(self, fp)


def load_po_file(path: Path) -> dict:
    """Load translations from a PO file.

    The function first attempts to compile the file with the external
    ``msgfmt`` command.  If that fails (e.g. the command is not available), a
    very small Python parser is used as a fallback so translations remain
    available without external dependencies.
    """
    entries: dict[tuple[str, str], str] = {}
    try:
        result = subprocess.run(
            ["msgfmt", "-o", "-", str(path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.debug(f"msgfmt failed for {path}: {exc}; using fallback parser")
        msgctxt = None
        msgid = None
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("msgctxt"):
                    msgctxt = line.split(" ", 1)[1].strip().strip('"')
                elif line.startswith("msgid"):
                    msgid = line.split(" ", 1)[1].strip().strip('"')
                elif line.startswith("msgstr"):
                    msgstr = line.split(" ", 1)[1].strip().strip('"')
                    if msgid:
                        entries[(msgctxt or "*", msgid)] = msgstr
                        msgctxt = None
                        msgid = None
        return entries
    else:
        trans = Utf8GNUTranslations(io.BytesIO(result.stdout))
        for key, msgstr in trans._catalog.items():
            if not key:
                continue
            if isinstance(key, tuple):
                msgctxt, msgid = key
            elif "\x04" in key:
                msgctxt, msgid = key.split("\x04", 1)
            else:
                msgctxt, msgid = "*", key
            entries[(msgctxt or "*", msgid)] = msgstr
        return entries

def init():
    global modules
    global ordered_classes
    modules = get_all_submodules(Path(__file__).parent)
    ordered_classes = get_ordered_classes_to_register(modules)

def register():
    # 初期化を呼び出して ordered_classes などをセット
    init()
    
    if modules is None or ordered_classes is None:
        logger.error("Failed to initialize modules or ordered_classes")
        return
    
    logger.info("Registering translations for FreePencil2...")
    logger.info(f"Available languages: {bpy.app.translations.locales}")
    logger.info(f"Current language: {bpy.context.preferences.view.language}")

    # Load translations from .po files
    global translation_dict
    translation_dict = {}
    locale_dir = Path(__file__).parent / "locale"
    for po_path in locale_dir.glob("*.po"):
        lang = po_path.stem
        try:
            translation_dict[lang] = load_po_file(po_path)
        except Exception as exc:
            logger.warning(f"Failed to load translation for {lang}: {exc}")

    try:
        bpy.app.translations.register(__name__, translation_dict)
        logger.info("Translation registration successful")
    except ValueError as e:
        if "translations message cache already contains" in str(e):
            logger.info(f"Translation for {__name__} already registered")
        else:
            raise
    
    from .props import register_props
    register_props()
    
    # 依存関係に従った順序で各クラスを登録
    for cls in ordered_classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            logger.warning(f"{cls.__name__} is already registered.")
    
    # 各サブモジュールに register() があれば呼び出す
    #for module in modules:
    #    if module.__name__ == __name__:
    #        continue
    #    if hasattr(module, "register"):
    #        module.register()

def unregister():
    logger.info("Unregistering translations for FreePencil2...")
    try:
        bpy.app.translations.unregister(__name__)
        logger.info("Translation unregistration successful")
    except ValueError:
        logger.info(f"Translation for {__name__} already unregistered")
    
    if modules is not None:
        for module in modules:
            if module.__name__ == __name__:
                continue
            #if hasattr(module, "unregister"):
            #    module.unregister()
    
    
    # 依存関係の逆順で各クラスを解除
    if ordered_classes is not None:
        for cls in reversed(ordered_classes):
            try:
                bpy.utils.unregister_class(cls)
            except RuntimeError:
                logger.warning(f"Could not unregister {cls.__name__}")
    
    from .props import unregister_props
    unregister_props()

# ------------------------------------------------------------
# サブモジュールの自動探索
# ------------------------------------------------------------

def get_all_submodules(directory):
    return list(iter_submodules(directory, __package__))

def iter_submodules(path, package_name):
    for name in sorted(iter_submodule_names(path)):
        yield importlib.import_module("." + name, package_name)

def iter_submodule_names(path, root=""):
    for _, module_name, is_package in pkgutil.iter_modules([str(path)]):
        if is_package:
            sub_path = path / module_name
            sub_root = root + module_name + "."
            yield from iter_submodule_names(sub_path, sub_root)
        else:
            yield root + module_name

# ------------------------------------------------------------
# 登録対象クラスの依存関係解決と順序決定
# ------------------------------------------------------------

def get_ordered_classes_to_register(modules):
    return toposort(get_register_deps_dict(modules))

def get_register_deps_dict(modules):
    my_classes = set(iter_my_classes(modules))
    my_classes_by_idname = {cls.bl_idname: cls for cls in my_classes if hasattr(cls, "bl_idname")}
    deps_dict = {}
    for cls in my_classes:
        deps_dict[cls] = set(iter_my_register_deps(cls, my_classes, my_classes_by_idname))
    return deps_dict

def iter_my_register_deps(cls, my_classes, my_classes_by_idname):
    yield from iter_my_deps_from_annotations(cls, my_classes)
    yield from iter_my_deps_from_parent_id(cls, my_classes_by_idname)

def iter_my_deps_from_annotations(cls, my_classes):
    for value in typing.get_type_hints(cls, {}, {}).values():
        dependency = get_dependency_from_annotation(value)
        if dependency is not None:
            if dependency in my_classes:
                yield dependency

def get_dependency_from_annotation(value):
    if blender_version >= (2, 93):
        if isinstance(value, bpy.props._PropertyDeferred):
            return value.keywords.get("type")
    else:
        if isinstance(value, tuple) and len(value) == 2:
            if value[0] in (bpy.props.PointerProperty, bpy.props.CollectionProperty):
                return value[1]["type"]
    return None

def iter_my_deps_from_parent_id(cls, my_classes_by_idname):
    if bpy.types.Panel in cls.__bases__:
        parent_idname = getattr(cls, "bl_parent_id", None)
        if parent_idname is not None:
            parent_cls = my_classes_by_idname.get(parent_idname)
            if parent_cls is not None:
                yield parent_cls

def iter_my_classes(modules):
    base_types = get_register_base_types()
    for cls in get_classes_in_modules(modules):
        if any(base in base_types for base in cls.__bases__):
            if not getattr(cls, "is_registered", False):
                yield cls

def get_classes_in_modules(modules):
    classes = set()
    for module in modules:
        for cls in iter_classes_in_module(module):
            classes.add(cls)
    return classes

def iter_classes_in_module(module):
    for value in module.__dict__.values():
        if inspect.isclass(value):
            yield value

def get_register_base_types():
    return set(getattr(bpy.types, name) for name in [
        "Panel", "Operator", "PropertyGroup",
        "AddonPreferences", "Header", "Menu",
        "Node", "NodeSocket", "NodeTree",
        "UIList", "RenderEngine",
        "Gizmo", "GizmoGroup",
    ])

# ------------------------------------------------------------
# トポロジカルソート（依存関係解決）
# ------------------------------------------------------------

def toposort(deps_dict):
    sorted_list = []
    sorted_values = set()
    while len(deps_dict) > 0:
        unsorted = []
        for value, deps in deps_dict.items():
            if len(deps) == 0:
                sorted_list.append(value)
                sorted_values.add(value)
            else:
                unsorted.append(value)
        deps_dict = {value: deps_dict[value] - sorted_values for value in unsorted}
    return sorted_list

