-- Reset business-facing tables so local business data can be reloaded safely.
SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE respuesta_estudiante;
TRUNCATE TABLE intento;
TRUNCATE TABLE cuestionario_preguntas;
TRUNCATE TABLE opcion;
TRUNCATE TABLE cuestionario;
TRUNCATE TABLE pregunta;
TRUNCATE TABLE usuario;

SET FOREIGN_KEY_CHECKS = 1;
