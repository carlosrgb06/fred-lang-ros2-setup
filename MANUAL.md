# FrED-LANG — Manual del Proyecto
## Capa de Control del Robot

> Documento de referencia técnica de la capa de control del brazo robótico
> UFACTORY xArm6 para el proyecto FrED-LANG.
>
> Última actualización: 2026-09-13

---

## Índice

1. [Introducción](#1-introducción)
2. [Visión general del sistema](#2-visión-general-del-sistema)
3. [Entorno de desarrollo](#3-entorno-de-desarrollo)
4. [La librería `FredArm`](#4-la-librería-fredarm)
5. [Notas de ingeniería](#5-notas-de-ingeniería)
6. [Guía de uso — ejemplos](#6-guía-de-uso--ejemplos)
7. [Trabajo futuro](#7-trabajo-futuro)
8. [Referencias](#8-referencias)

---

## 1. Introducción

<!-- PENDIENTE -->

---

## 2. Visión general del sistema

<!-- PENDIENTE -->

---

## 3. Entorno de desarrollo

<!-- PENDIENTE -->

---

## 4. La librería `FredArm`

<!-- ============================================================
     SECCIÓN EN CONSTRUCCIÓN — empezamos por aquí
     ============================================================ -->

### 4.1 Arquitectura en capas

`FredArm` está organizada como una **jerarquía de abstracción**: cada capa usa la de
abajo y esconde su complejidad. El código de más alto nivel (y en el futuro, el generado
por el LLM) trabaja con verbos semánticos, sin preocuparse por los detalles de los
servicios ROS2 subyacentes.

```
┌───────────────────────────────────────────────────────────────────────┐
│  Capa 3 — Primitivas de alto nivel        home()  mover_a()  agarrar()  │  (en construcción)
│           (verbos semánticos)                                          │
├───────────────────────────────────────────────────────────────────────┤
│  Capa 2 — Lectura y verificación de       esperar_listo()  hay_error() │
│           estado                          servos_ok()  get_angulos()   │
├───────────────────────────────────────────────────────────────────────┤
│  Capa 1 — Cliente de servicios /xarm/*    motion_enable()  set_mode()  │
│           (control de bajo nivel)         set_state()  set_position()  │
│                                           set_servo_angle()            │
│                                           move_gohome()  clean_error() │
├───────────────────────────────────────────────────────────────────────┤
│  Capa 0 — Driver xarm_api (C++) + ROS2    servicios y tópicos /xarm/*  │
└───────────────────────────────────────────────────────────────────────┘
```

Organizar la clase `FredArm` en estas capas asegura que el LLM que controlará el xArm
tenga todo lo necesario para moverlo, y a la vez disponga de herramientas de alto nivel
que faciliten el uso de la librería. El objetivo del proyecto es traducir lenguaje natural
a código Python, y para un LLM es mucho más sencillo convertir una instrucción como
*"mueve la pieza roja de la posición A a la posición B"* en código que usa verbos
semánticos:

```python
agarrar()
mover_a(...)
soltar()
```

...que en código que orquesta directamente los servicios de bajo nivel del firmware:

```python
motion_enable()
set_mode()
set_state()
set_position(...)
```

Esta separación da una doble ventaja. Por un lado, las primitivas de alto nivel encapsulan
secuencias ya validadas: el LLM no puede equivocarse en *cómo* se ejecuta un movimiento,
solo en *cuándo* — lo que reduce la superficie de error y refuerza el principio de
**seguridad** del proyecto. Por otro, un script escrito con estos verbos se lee como una
receta, lo que sostiene el principio de **interpretabilidad**: cualquiera puede auditar qué
hará el robot sin descifrar llamadas de bajo nivel.

Al mismo tiempo, mantener expuesta la Capa 1 conserva el acceso directo a los servicios del
firmware para casos que las primitivas no cubran (depuración, movimientos especiales,
control fino). La librería se diseñó contemplando ambos escenarios: facilitar el trabajo
del LLM sin sacrificar el control de bajo nivel.

> **Nota:** la separación en capas es *conceptual*, no física. Todos los métodos viven en
> la misma clase `FredArm`; las capas describen niveles de abstracción, no clases o
> archivos distintos.

### 4.2 Anatomía de un método

Todos los métodos que llaman a un servicio siguen el mismo patrón (el "molde"):

```
1. Construir el request         request = TipoServicio.Request()
2. Llenar sus campos            request.campo = valor
3. Enviar de forma asíncrona    future = cliente.call_async(request)
4. Esperar la respuesta         rclpy.spin_until_future_complete(self, future)
5. Leer el resultado            return future.result().ret
```

En el sistema de servicios de ROS2, las llamadas y sus respuestas no llegan al instante:
los procesos que emplean parte de las funciones de `FredArm` son **asíncronos**. Cuando
usamos `call_async`, este no nos devuelve la respuesta que esperamos, sino un **`future`**
que en términos simples es una promesa de que llegará un resultado más adelante.

Por eso necesitamos `spin_until_future_complete`: este corre el executor de ROS2 hasta que
ese `future` se completa, y solo entonces nos devuelve el control. Es el **puente** entre
los procesos asíncronos de ROS2 y una API síncrona cómoda de usar, como la que exponemos
en nuestro código:

```python
ret = arm.set_mode(0)
```

Desde el punto de vista de quien llama, esa línea se comporta como una función normal:
bloquea hasta tener el resultado y devuelve el `ret` directamente. Toda la complejidad
asíncrona queda encapsulada dentro del método, de modo que las capas superiores y el
LLM pueden encadenar comandos sin lidiar con `future`s ni con el executor.

### 4.3 Referencia de la API — Capa 1

<!-- TU TEXTO: aquí va la referencia método por método. Sugiero una subsección
     por grupo. Tus docstrings ya son la materia prima. -->

#### Arranque

<!-- motion_enable, set_mode, set_state -->

#### Movimiento

<!-- set_position, set_servo_angle, move_gohome -->

#### Lectura de estado

<!-- suscripción robot_states, hay_error, servos_ok, esperar_listo, get_angulos -->

#### Recuperación

<!-- clean_error -->

### 4.4 Conceptos clave

<!-- TU TEXTO: los conceptos que hay que entender para usar bien la librería. -->

#### Espacio articular vs. espacio cartesiano

<!-- joint-space vs Cartesian-space -->

#### La máquina de estados y modos del xArm

<!-- tablas de state y mode -->

#### Estados fijados vs. estados leídos

<!-- set_state(0) se reporta como state:2 -->

#### Unidades

<!-- rad para ángulos; mm + rad para pose -->

---

## 5. Notas de ingeniería

<!-- PENDIENTE -->

---

## 6. Guía de uso — ejemplos

<!-- PENDIENTE -->

---

## 7. Trabajo futuro

<!-- PENDIENTE -->

---

## 8. Referencias

<!-- PENDIENTE -->
