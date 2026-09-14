# FrED-LANG — Manual del Proyecto
## Capa de Control del Robot

> Documento de referencia técnica de la capa de control del brazo robótico
> UFACTORY xArm6 para el proyecto FrED-LANG.
>
> Última actualización: 2026-09-14

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

<!-- TU TEXTO: explica en tus palabras por qué el diseño en capas, y qué gana el
     proyecto con esta separación. -->

### 4.2 Anatomía de un método

Todos los métodos que llaman a un servicio siguen el mismo patrón (el "molde"):

```
1. Construir el request         request = TipoServicio.Request()
2. Llenar sus campos            request.campo = valor
3. Enviar de forma asíncrona    future = cliente.call_async(request)
4. Esperar la respuesta         rclpy.spin_until_future_complete(self, future)
5. Leer el resultado            return future.result().ret
```

<!-- TU TEXTO: explica el porqué de call_async + spin_until_future_complete
     (el tema del hilo del executor, por qué no es síncrono directo). -->

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
