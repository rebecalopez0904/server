from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.utils.text import slugify


PLANTILLAS_DIRNAME = "plantillas"
PREDETERMINADAS_DIRNAME = "predeterminadas"
PROPIAS_DIRNAME = "propias"


def get_templates_root() -> Path:
	return Path(settings.MEDIA_ROOT) / PLANTILLAS_DIRNAME


def get_default_templates_dir() -> Path:
	return get_templates_root() / PREDETERMINADAS_DIRNAME


def get_custom_templates_dir() -> Path:
	return get_templates_root() / PROPIAS_DIRNAME


def ensure_templates_media_structure() -> dict[str, Path]:
	paths = {
		"root": get_templates_root(),
		"predeterminadas": get_default_templates_dir(),
		"propias": get_custom_templates_dir(),
	}
	for directory in paths.values():
		directory.mkdir(parents=True, exist_ok=True)
	return paths


def normalize_user_folder_name(raw_user_reference: str | int) -> str:
	value = str(raw_user_reference).strip()
	if not value:
		raise ValueError("El identificador del usuario no puede estar vacío.")

	folder_name = slugify(value).replace("-", "_")
	if not folder_name:
		raise ValueError("No fue posible generar un nombre de carpeta válido.")

	return folder_name


def normalize_template_relative_path(relative_path: str) -> Path:
	if not relative_path or not relative_path.strip():
		raise SuspiciousFileOperation("La ruta de la plantilla no puede estar vacía.")

	clean_path = PurePosixPath(relative_path.replace("\\", "/"))
	if clean_path.is_absolute():
		raise SuspiciousFileOperation("No se permiten rutas absolutas.")

	parts = [part for part in clean_path.parts if part not in {"", "."}]
	if not parts or any(part == ".." for part in parts):
		raise SuspiciousFileOperation("La ruta de la plantilla no es segura.")

	return Path(*parts)


def ensure_path_within_base(base_dir: Path, target_path: Path) -> Path:
	base = base_dir.resolve()
	target = target_path.resolve()
	try:
		target.relative_to(base)
	except ValueError as exc:
		raise SuspiciousFileOperation("La ruta de la plantilla sale del directorio permitido.") from exc
	return target


def resolve_custom_template_storage_path(
	user_reference: str | int,
	relative_path: str,
	*,
	create_parent: bool = False,
) -> Path:
	structure = ensure_templates_media_structure()
	user_folder = normalize_user_folder_name(user_reference)
	user_base = structure["propias"] / user_folder
	user_base.mkdir(parents=True, exist_ok=True)

	normalized_relative = normalize_template_relative_path(relative_path)
	target_path = ensure_path_within_base(user_base, user_base / normalized_relative)

	if create_parent:
		target_path.parent.mkdir(parents=True, exist_ok=True)

	return target_path
