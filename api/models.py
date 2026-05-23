from django.db import models


class Usuario(models.Model):
	id_usuario = models.AutoField(primary_key=True, db_column="ID_usuario")
	nombre_usuario = models.CharField(max_length=50)
	apellido_usuario = models.CharField(max_length=50)
	correo = models.CharField(max_length=100, unique=True)
	contrasena = models.CharField(max_length=255)
	rol = models.CharField(max_length=20)

	class Meta:
		db_table = "usuario"

	def __str__(self):
		return f"{self.nombre_usuario} {self.apellido_usuario}"

	@property
	def is_authenticated(self):
		return True

	@property
	def is_anonymous(self):
		return False


class RefreshTokenSession(models.Model):
	id_refresh_token = models.AutoField(primary_key=True, db_column="ID_refresh_token")
	usuario = models.ForeignKey(
		Usuario,
		on_delete=models.CASCADE,
		db_column="ID_usuario",
		related_name="refresh_tokens",
	)
	jti = models.CharField(max_length=36, unique=True)
	token_hash = models.CharField(max_length=64)
	expira_en = models.DateTimeField()
	revocado_en = models.DateTimeField(null=True, blank=True)
	creado_en = models.DateTimeField(auto_now_add=True)

	class Meta:
		db_table = "refresh_token_session"


class Pregunta(models.Model):
	id_pregunta = models.AutoField(primary_key=True, db_column="ID_pregunta")
	enunciado = models.TextField()
	figura_correcta_canva = models.CharField(max_length=50, null=True, blank=True)
	plantilla_url = models.TextField(null=True, blank=True)
	@property
    def get_full_plantilla_url(self):
        if self.plantilla_url:
            # Si ya es una URL completa (de Cloudinary), la devolvemos tal cual
            if self.plantilla_url.startswith("http"):
                return self.plantilla_url
            # Si solo es el nombre del archivo, le añadimos el prefijo
            return f"{settings.CLOUDINARY_BASE_URL}{self.plantilla_url}"
        return None
	
	retro_trazado = models.TextField(null=True, blank=True)
	retro_opciones = models.TextField(null=True, blank=True)
	usuario_creador = models.ForeignKey(
		Usuario,
		on_delete=models.PROTECT,
		db_column="ID_usuario_creador",
		null=True,
		blank=True,
		related_name="preguntas_creadas",
	)
	nivel = models.CharField(max_length=20)

	class Meta:
		db_table = "pregunta"


class Opcion(models.Model):
	id_opcion = models.AutoField(primary_key=True, db_column="ID_opcion")
	pregunta = models.ForeignKey(
		Pregunta,
		on_delete=models.PROTECT,
		db_column="ID_pregunta",
		related_name="opciones",
	)
	texto_opcion = models.CharField(max_length=255)
	es_correcta = models.BooleanField()

	class Meta:
		db_table = "opcion"


class Cuestionario(models.Model):
	id_cuestionario = models.AutoField(primary_key=True, db_column="ID_cuestionario")
	profesor = models.ForeignKey(
		Usuario,
		on_delete=models.PROTECT,
		db_column="ID_profesor",
		related_name="cuestionarios_creados",
	)
	nombre = models.CharField(max_length=100)
	codigo = models.CharField(max_length=50, unique=True)
	fecha = models.DateField()
	activo_estatus = models.BooleanField()
	preguntas = models.ManyToManyField(
		Pregunta,
		through="CuestionarioPregunta",
		related_name="cuestionarios",
	)

	class Meta:
		db_table = "cuestionario"


class CuestionarioPregunta(models.Model):
	pk = models.CompositePrimaryKey("cuestionario", "pregunta")
	cuestionario = models.ForeignKey(
		Cuestionario,
		on_delete=models.CASCADE,
		db_column="ID_cuestionario",
	)
	pregunta = models.ForeignKey(
		Pregunta,
		on_delete=models.PROTECT,
		db_column="ID_pregunta",
	)

	class Meta:
		db_table = "cuestionario_preguntas"


class Intento(models.Model):
	id_intento = models.AutoField(primary_key=True, db_column="ID_intento")
	estudiante = models.ForeignKey(
		Usuario,
		on_delete=models.PROTECT,
		db_column="ID_estudiante",
		related_name="intentos",
	)
	cuestionario = models.ForeignKey(
		Cuestionario,
		on_delete=models.CASCADE,
		db_column="ID_cuestionario",
		related_name="intentos",
	)
	fecha_intento = models.DateField()
	calificacion_final = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		null=True,
		blank=True,
	)

	class Meta:
		db_table = "intento"


class RespuestaEstudiante(models.Model):
	pk = models.CompositePrimaryKey("intento", "pregunta")
	intento = models.ForeignKey(
		Intento,
		on_delete=models.CASCADE,
		db_column="ID_intento",
	)
	pregunta = models.ForeignKey(
		Pregunta,
		on_delete=models.PROTECT,
		db_column="ID_pregunta",
	)
	opc_select = models.ForeignKey(
		Opcion,
		on_delete=models.PROTECT,
		db_column="ID_opc_select",
		null=True,
		blank=True,
	)
	datos_trazado = models.TextField(null=True, blank=True)
	prediccion_ia = models.CharField(max_length=50, null=True, blank=True)
	precision_ia = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		null=True,
		blank=True,
	)
	calificacion_pregunta = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		null=True,
		blank=True,
	)
	retro_individual = models.TextField(null=True, blank=True)

	class Meta:
		db_table = "respuesta_estudiante"
