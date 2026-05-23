import shutil
from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Opcion, Pregunta, Usuario
from .security import create_access_token
from .template_storage import (
	ensure_templates_media_structure,
	normalize_template_relative_path,
	normalize_user_folder_name,
	resolve_custom_template_storage_path,
)


class AuthRegressionTests(APITestCase):
	def setUp(self):
		self.usuario = Usuario.objects.create(
			nombre_usuario="Ana",
			apellido_usuario="Lopez",
			correo="ana@example.com",
			contrasena="dummy-password",
			rol="profesor",
		)
		self.usuarios_url = reverse("usuario-list")

	def test_protected_list_with_valid_jwt_returns_200(self):
		token = create_access_token(self.usuario)
		response = self.client.get(
			self.usuarios_url,
			HTTP_AUTHORIZATION=f"Bearer {token}",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertNotEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

	def test_protected_list_without_token_returns_401(self):
		response = self.client.get(self.usuarios_url)

		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
		self.assertNotEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

	def test_protected_list_with_invalid_token_returns_401(self):
		response = self.client.get(
			self.usuarios_url,
			HTTP_AUTHORIZATION="Bearer invalid.token.value",
		)

		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
		self.assertNotEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


@override_settings(MEDIA_ROOT=Path(__file__).resolve().parent.parent / "_test_media_structure")
class TemplateStorageHelpersTests(APITestCase):
	def tearDown(self):
		super().tearDown()
		shutil.rmtree(Path(settings.MEDIA_ROOT), ignore_errors=True)

	def test_ensure_templates_media_structure_creates_expected_dirs(self):
		paths = ensure_templates_media_structure()

		self.assertTrue(paths["root"].is_dir())
		self.assertTrue(paths["predeterminadas"].is_dir())
		self.assertTrue(paths["propias"].is_dir())

	def test_normalize_user_folder_name(self):
		self.assertEqual(normalize_user_folder_name(" Nombre Profesor 01 "), "nombre_profesor_01")

	def test_normalize_template_relative_path_rejects_traversal(self):
		with self.assertRaises(SuspiciousFileOperation):
			normalize_template_relative_path("../secreto.svg")

	def test_resolve_custom_template_storage_path_normalizes_windows_separator(self):
		resolved = resolve_custom_template_storage_path("Profesor 01", r"subcarpeta\plantilla.svg")

		expected = (
			Path(settings.MEDIA_ROOT)
			/ "plantillas"
			/ "propias"
			/ "profesor_01"
			/ "subcarpeta"
			/ "plantilla.svg"
		).resolve()
		self.assertEqual(resolved, expected)

	def test_resolve_custom_template_storage_path_rejects_escape(self):
		with self.assertRaises(SuspiciousFileOperation):
			resolve_custom_template_storage_path("Profesor 01", "../../otra-carpeta/plantilla.svg")


@override_settings(
	MEDIA_ROOT=Path(__file__).resolve().parent.parent / "_test_media_templates_api",
	TEMPLATE_UPLOAD_MAX_SIZE=1024,
)
class PlantillaPropiaAPITests(APITestCase):
	def setUp(self):
		super().setUp()
		self.profesor = Usuario.objects.create(
			nombre_usuario="Luis",
			apellido_usuario="Perez",
			correo="luis@example.com",
			contrasena="dummy-password",
			rol="profesor",
		)
		self.estudiante = Usuario.objects.create(
			nombre_usuario="Eva",
			apellido_usuario="Ruiz",
			correo="eva@example.com",
			contrasena="dummy-password",
			rol="estudiante",
		)
		self.upload_url = reverse("plantilla-propia-upload")
		self.list_url = reverse("plantilla-propia-list")
		self.default_list_url = reverse("plantilla-predeterminada-list")

	def tearDown(self):
		super().tearDown()
		shutil.rmtree(Path(settings.MEDIA_ROOT), ignore_errors=True)

	def _authorize(self, user):
		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")

	def test_profesor_can_upload_list_and_delete_own_template(self):
		self._authorize(self.profesor)
		archivo = SimpleUploadedFile(
			"Figura Final.svg",
			b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
			content_type="image/svg+xml",
		)
		upload_response = self.client.post(
			self.upload_url,
			{"archivo": archivo},
			format="multipart",
		)
		self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
		self.assertIn("plantilla_url", upload_response.data)
		self.assertIn("plantilla_path", upload_response.data)

		list_response = self.client.get(self.list_url)
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data["results"]), 1)

		template_name = upload_response.data["nombre_archivo"]
		delete_url = reverse("plantilla-propia-delete", kwargs={"template_name": template_name})
		delete_response = self.client.delete(delete_url)
		self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

	def test_non_profesor_cannot_manage_templates(self):
		self._authorize(self.estudiante)
		response = self.client.get(self.list_url)
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
		default_response = self.client.get(self.default_list_url)
		self.assertEqual(default_response.status_code, status.HTTP_403_FORBIDDEN)

	def test_profesor_can_list_default_templates(self):
		self._authorize(self.profesor)
		structure = ensure_templates_media_structure()
		default_dir = structure["predeterminadas"]
		(default_dir / "zeta.svg").write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
		(default_dir / "alpha.png").write_bytes(b"png")
		(default_dir / "ignorar.txt").write_text("no permitido", encoding="utf-8")

		response = self.client.get(self.default_list_url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		results = response.data["results"]
		self.assertEqual(len(results), 2)
		self.assertEqual(results[0]["nombre_archivo"], "alpha.png")
		self.assertEqual(results[1]["nombre_archivo"], "zeta.svg")

	def test_upload_rejects_invalid_extension(self):
		self._authorize(self.profesor)
		archivo = SimpleUploadedFile("nota.txt", b"hola", content_type="text/plain")
		response = self.client.post(
			self.upload_url,
			{"archivo": archivo},
			format="multipart",
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_upload_rejects_oversized_files(self):
		self._authorize(self.profesor)
		archivo = SimpleUploadedFile(
			"grande.svg",
			b"x" * 2048,
			content_type="image/svg+xml",
		)
		response = self.client.post(
			self.upload_url,
			{"archivo": archivo},
			format="multipart",
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_delete_rejects_template_in_use(self):
		self._authorize(self.profesor)
		archivo = SimpleUploadedFile(
			"referenciada.svg",
			b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
			content_type="image/svg+xml",
		)
		upload_response = self.client.post(
			self.upload_url,
			{"archivo": archivo},
			format="multipart",
		)
		self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)

		Pregunta.objects.create(
			enunciado="Pregunta con plantilla",
			plantilla_url=upload_response.data["plantilla_url"],
			nivel="basico",
			usuario_creador=self.profesor,
		)

		delete_url = reverse(
			"plantilla-propia-delete",
			kwargs={"template_name": upload_response.data["nombre_archivo"]},
		)
		delete_response = self.client.delete(delete_url)
		self.assertEqual(delete_response.status_code, status.HTTP_409_CONFLICT)

	def test_delete_question_cleans_unused_template_file(self):
		self._authorize(self.profesor)
		archivo = SimpleUploadedFile(
			"limpieza.svg",
			b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
			content_type="image/svg+xml",
		)
		upload_response = self.client.post(
			self.upload_url,
			{"archivo": archivo},
			format="multipart",
		)
		self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)

		template_name = upload_response.data["nombre_archivo"]
		template_path = resolve_custom_template_storage_path(self.profesor.id_usuario, template_name)
		self.assertTrue(template_path.exists())

		question = Pregunta.objects.create(
			enunciado="Pregunta con plantilla temporal",
			plantilla_url=upload_response.data["plantilla_url"],
			figura_correcta_canva="circulo",
			nivel="basico",
			usuario_creador=self.profesor,
		)
		delete_response = self.client.delete(
			reverse("pregunta-detail", kwargs={"pk": question.id_pregunta})
		)

		self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
		self.assertFalse(template_path.exists())

	def test_update_question_template_to_null_cleans_unused_template_file(self):
		self._authorize(self.profesor)
		archivo = SimpleUploadedFile(
			"quitar_plantilla.svg",
			b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
			content_type="image/svg+xml",
		)
		upload_response = self.client.post(
			self.upload_url,
			{"archivo": archivo},
			format="multipart",
		)
		self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)

		template_name = upload_response.data["nombre_archivo"]
		template_path = resolve_custom_template_storage_path(self.profesor.id_usuario, template_name)
		self.assertTrue(template_path.exists())

		question = Pregunta.objects.create(
			enunciado="Pregunta para quitar plantilla",
			plantilla_url=upload_response.data["plantilla_url"],
			figura_correcta_canva="triangulo",
			nivel="basico",
			usuario_creador=self.profesor,
		)
		patch_response = self.client.patch(
			reverse("pregunta-detail", kwargs={"pk": question.id_pregunta}),
			{"plantilla_url": None},
			format="json",
		)

		self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
		self.assertFalse(template_path.exists())


class DefaultsReadonlyEnforcementTests(APITestCase):
	def setUp(self):
		super().setUp()
		self.profesor = Usuario.objects.create(
			nombre_usuario="Mario",
			apellido_usuario="Diaz",
			correo="mario@example.com",
			contrasena="dummy-password",
			rol="profesor",
		)
		self.predeterminada = Pregunta.objects.create(
			enunciado="Pregunta predeterminada",
			nivel="basico",
			usuario_creador=None,
		)
		self.propia = Pregunta.objects.create(
			enunciado="Pregunta propia",
			nivel="basico",
			usuario_creador=self.profesor,
		)
		self.predeterminada_opcion = Opcion.objects.create(
			pregunta=self.predeterminada,
			texto_opcion="Pred A",
			es_correcta=True,
		)
		self.propia_opcion = Opcion.objects.create(
			pregunta=self.propia,
			texto_opcion="Propia A",
			es_correcta=False,
		)
		self.client.credentials(
			HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.profesor)}"
		)

	def test_cannot_update_or_delete_predeterminada_question(self):
		pregunta_url = reverse(
			"pregunta-detail", kwargs={"pk": self.predeterminada.id_pregunta}
		)

		patch_response = self.client.patch(
			pregunta_url,
			{"enunciado": "Cambio", "figura_correcta_canva": "circulo"},
		)
		delete_response = self.client.delete(pregunta_url)

		self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)

	def test_can_update_and_delete_propia_question(self):
		pregunta_url = reverse("pregunta-detail", kwargs={"pk": self.propia.id_pregunta})

		patch_response = self.client.patch(
			pregunta_url,
			{"enunciado": "Cambio propio", "figura_correcta_canva": "triangulo"},
		)
		self.assertEqual(patch_response.status_code, status.HTTP_200_OK)

		pregunta_eliminable = Pregunta.objects.create(
			enunciado="Sin opciones",
			nivel="intermedio",
			usuario_creador=self.profesor,
		)
		delete_response = self.client.delete(
			reverse("pregunta-detail", kwargs={"pk": pregunta_eliminable.id_pregunta})
		)
		self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

	def test_cannot_create_predeterminada_question_from_management_endpoint(self):
		response = self.client.post(
			reverse("pregunta-list"),
			{
				"enunciado": "Intento predeterminada",
				"nivel": "intermedio",
				"figura_correcta_canva": "circulo",
				"usuario_creador": None,
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_cannot_create_question_without_figure_and_options(self):
		response = self.client.post(
			reverse("pregunta-list"),
			{
				"enunciado": "Pregunta inválida",
				"nivel": "basico",
				"usuario_creador": self.profesor.id_usuario,
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_can_create_question_with_options_only(self):
		response = self.client.post(
			reverse("pregunta-list"),
			{
				"enunciado": "Pregunta válida con opciones",
				"nivel": "basico",
				"usuario_creador": self.profesor.id_usuario,
				"opciones": [
					{"texto_opcion": "A", "es_correcta": True},
					{"texto_opcion": "B", "es_correcta": False},
				],
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		question_id = response.data["id_pregunta"]
		self.assertEqual(
			Opcion.objects.filter(pregunta_id=question_id).count(),
			2,
		)

	def test_cannot_create_update_or_delete_option_for_predeterminada_question(self):
		opciones_url = reverse("opcion-list")
		pred_opcion_url = reverse(
			"opcion-detail", kwargs={"pk": self.predeterminada_opcion.id_opcion}
		)

		create_response = self.client.post(
			opciones_url,
			{
				"pregunta": self.predeterminada.id_pregunta,
				"texto_opcion": "Nueva",
				"es_correcta": False,
			},
			format="json",
		)
		update_response = self.client.patch(
			pred_opcion_url,
			{"texto_opcion": "Cambio"},
			format="json",
		)
		delete_response = self.client.delete(pred_opcion_url)

		self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)

	def test_cannot_retarget_option_to_predeterminada_question(self):
		prop_opcion_url = reverse(
			"opcion-detail", kwargs={"pk": self.propia_opcion.id_opcion}
		)

		response = self.client.patch(
			prop_opcion_url,
			{"pregunta": self.predeterminada.id_pregunta},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_can_manage_options_for_propias(self):
		opciones_url = reverse("opcion-list")
		prop_opcion_url = reverse(
			"opcion-detail", kwargs={"pk": self.propia_opcion.id_opcion}
		)

		create_response = self.client.post(
			opciones_url,
			{
				"pregunta": self.propia.id_pregunta,
				"texto_opcion": "Nueva propia",
				"es_correcta": True,
			},
			format="json",
		)
		update_response = self.client.patch(
			prop_opcion_url,
			{"texto_opcion": "Cambio propio"},
			format="json",
		)
		delete_response = self.client.delete(prop_opcion_url)

		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(update_response.status_code, status.HTTP_200_OK)
		self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
