# server/api/serializers.py
from rest_framework import serializers

from .models import (
	Cuestionario,
	CuestionarioPregunta,
	Intento,
	Opcion,
	Pregunta,
	RespuestaEstudiante,
	Usuario,
)
from .security import hash_password, is_bcrypt_hash


class UsuarioSerializer(serializers.ModelSerializer):
	contrasena = serializers.CharField(write_only=True, required=False)

	def validate_contrasena(self, value):
		if len(value) < 8:
			raise serializers.ValidationError(
				"La contrasena debe tener al menos 8 caracteres."
			)
		return value

	def create(self, validated_data):
		raw_password = validated_data.pop("contrasena", None)
		if raw_password is None:
			raise serializers.ValidationError(
				{"contrasena": "La contrasena es obligatoria."}
			)
		validated_data["contrasena"] = hash_password(raw_password)
		return super().create(validated_data)

	def update(self, instance, validated_data):
		raw_password = validated_data.get("contrasena")
		if raw_password:
			if not is_bcrypt_hash(raw_password):
				validated_data["contrasena"] = hash_password(raw_password)
		elif raw_password == "":
			raise serializers.ValidationError(
				{"contrasena": "La contrasena no puede estar vacia."}
			)
		return super().update(instance, validated_data)

	class Meta:
		model = Usuario
		fields = "__all__"


class AuthRegisterSerializer(serializers.Serializer):
	nombre_usuario = serializers.CharField(max_length=50)
	apellido_usuario = serializers.CharField(max_length=50)
	correo = serializers.EmailField(max_length=100)
	contrasena = serializers.CharField(write_only=True, min_length=8, max_length=128)
	rol = serializers.ChoiceField(choices=["profesor", "estudiante"])


class AuthLoginSerializer(serializers.Serializer):
	correo = serializers.EmailField(max_length=100)
	contrasena = serializers.CharField(write_only=True, max_length=128)


class PreguntaSerializer(serializers.ModelSerializer):
	opciones = serializers.ListField(
		child=serializers.DictField(),
		write_only=True,
		required=False,
	)

	def _normalize_options(self, raw_options):
		normalized = []
		for option in raw_options or []:
			text = str(option.get("texto_opcion") or option.get("text") or "").strip()
			if not text:
				continue
			normalized.append(
				{
					"texto_opcion": text,
					"es_correcta": bool(option.get("es_correcta") or option.get("isCorrect")),
				}
			)
		return normalized

	def validate(self, attrs):
		enunciado = attrs.get("enunciado")
		if enunciado is None and self.instance is not None:
			enunciado = self.instance.enunciado
		if not str(enunciado or "").strip():
			raise serializers.ValidationError(
				{"enunciado": "El enunciado es obligatorio."}
			)

		figura = attrs.get("figura_correcta_canva")
		if figura is None and self.instance is not None:
			figura = self.instance.figura_correcta_canva
		has_figura = bool(str(figura or "").strip())

		incoming_options = attrs.get("opciones", None)
		normalized_options = self._normalize_options(incoming_options)
		has_options = bool(normalized_options)
		if incoming_options is None and self.instance is not None:
			has_options = self.instance.opciones.exists()

		if not has_figura and not has_options:
			raise serializers.ValidationError(
				{
					"non_field_errors": [
						"La pregunta debe incluir al menos una opción o una figura a trazar."
					]
				}
			)
		if normalized_options and not any(
			option["es_correcta"] for option in normalized_options
		):
			raise serializers.ValidationError(
				{
					"opciones": [
						"Si agregas opciones, marca una respuesta correcta."
					]
				}
			)
		attrs["opciones"] = normalized_options
		return attrs

	def create(self, validated_data):
		options_payload = validated_data.pop("opciones", [])
		pregunta = super().create(validated_data)
		for option in options_payload:
			Opcion.objects.create(pregunta=pregunta, **option)
		return pregunta
		
	full_plantilla_url = serializers.ReadOnlyField(source='get_full_plantilla_url')
	
	class Meta:
		model = Pregunta
		fields = "__all__"


class OpcionSerializer(serializers.ModelSerializer):
	class Meta:
		model = Opcion
		fields = "__all__"


class CuestionarioSerializer(serializers.ModelSerializer):
	class Meta:
		model = Cuestionario
		fields = "__all__"


class CuestionarioPreguntaSerializer(serializers.ModelSerializer):
	class Meta:
		model = CuestionarioPregunta
		fields = "__all__"
		read_only_fields = ["pk"]


class IntentoSerializer(serializers.ModelSerializer):
	class Meta:
		model = Intento
		fields = "__all__"


class RespuestaEstudianteSerializer(serializers.ModelSerializer):
	class Meta:
		model = RespuestaEstudiante
		fields = "__all__"
		read_only_fields = ["pk"]
