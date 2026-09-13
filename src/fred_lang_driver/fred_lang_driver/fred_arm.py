import rclpy
from rclpy.node import Node
from xarm_msgs.srv import SetInt16ById, SetInt16, MoveJoint, MoveCartesian



class FredArm(Node):
    """Cliente ROS2 de los servicios /xarm/* para controlar un brazo UFACTORY.

    Envuelve el driver oficial xarm_api (no el SDK de Python) exponiendo
    métodos de arranque (motion_enable, set_mode, set_state) y de movimiento
    (set_servo_angle en joint space, set_position en cartesian space). El mismo
    código sirve para el simulador y el hardware real cambiando robot_ip.
    """
    def __init__(self):
        super().__init__('fred_arm_node')
        self.motion_enable_client = self._make_client(SetInt16ById, '/xarm/motion_enable')
        self.set_state_client = self._make_client(SetInt16, '/xarm/set_state')
        self.set_mode_client = self._make_client(SetInt16, '/xarm/set_mode')
        self.set_servo_angle_client = self._make_client(MoveJoint, '/xarm/set_servo_angle')
        self.set_position_client = self._make_client(MoveCartesian, '/xarm/set_position')

    def _make_client(self, srv_type, srv_name):
        """Crea un cliente de servicio y espera a que esté disponible.

        Args:
            srv_type: la clase del servicio (ej. SetInt16, SetInt16ById).
            srv_name (str): el nombre del servicio (ej. '/xarm/set_mode').

        Returns:
            el cliente listo para usar.

        Raises:
            RuntimeError: si el servicio no aparece en el timeout (driver no corriendo).
        """
        client = self.create_client(srv_type, srv_name)
        if not client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error(f'{srv_name} service not available')
            raise RuntimeError('xarm_api driver not running')
        return client

    def motion_enable(self, enable, id=8):
        """Habilita o deshabilita los servomotores del brazo.

        Debe llamarse ANTES de set_mode y set_state en la secuencia de arranque.

        Args:
            enable (int): 1 = habilitar, 0 = deshabilitar.
            id (int): servo objetivo. 1-7 para un eje individual,
                8 = todos los ejes a la vez (default).

        Returns:
            int: ret del driver. 0 = éxito. NOTA: contra el firmware sim
                devuelve ret=3 (timeout cosmético) pero los servos SÍ se
                habilitan; verificar mt_able en /xarm/robot_states.
        """
        request = SetInt16ById.Request()
        request.id = id
        request.data = enable
        future = self.motion_enable_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'motion_enable(enable={enable}, id={id}) -> ret={response.ret}')
        return response.ret

    def set_mode(self, mode):
        """Fija el modo de operación del brazo.

        Debe fijarse antes de set_state(0), con el brazo en STOP/STANDBY.

        Args:
            mode (int): modo de control.
                0 = posición, control punto a punto (default). Para
                    set_position / set_servo_angle. <- usar este en el flujo actual.
                1 = servoj, planificador de trayectoria externo (MoveIt/ros-controllers).
                2 = manual / Free-Drive (gravedad cero).
                3 = reservado.
                4 = control de velocidad articular.
                5 = control de velocidad cartesiana.
                6 = planificación dinámica online en espacio articular (firmware >= v1.10.0).
                7 = planificación dinámica online en espacio cartesiano (firmware >= v1.11.0).

        Returns:
            int: ret del driver. 0 = éxito.
        """
        request = SetInt16.Request()
        request.data = mode
        future = self.set_mode_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'set_mode(mode={mode}) -> ret={response.ret}')
        return response.ret

    def set_state(self, state):
        """Fija el estado del brazo.

        Llamar con 0 al final de la secuencia de arranque para dejar el brazo
        listo para moverse.

        Args:
            state (int): estado a fijar (OJO: los valores que se FIJAN no son
                los mismos que se LEEN en /xarm/robot_states).
                0 = STANDBY: pone el brazo listo en el modo actual y limpia
                    errores. El feedback pasará a 2 (READY) automáticamente.
                3 = PAUSED: pausa la ejecución; se reanuda con set_state(0).
                4 = STOP: termina toda ejecución de inmediato; no acepta
                    comandos nuevos hasta volver a STANDBY (0).

        Returns:
            int: ret del driver. 0 = éxito.

        Nota: los estados LEÍDOS en /xarm/robot_states usan otra tabla:
            1 = en movimiento, 2 = ready (sin movimiento), 3 = pausado,
            4 = deteniéndose. Por eso set_state(0) reporta 2 en el feedback.
        """
        request = SetInt16.Request()
        request.data = state
        future = self.set_state_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'set_state(state={state}) -> ret={response.ret}')
        return response.ret

    def set_servo_angle(self, angles, speed = 0.35, acc = 10.0, wait=True):
        """Mueve el brazo en espacio articular (joint space).

        Especifica el ángulo de cada junta directamente; el brazo no resuelve
        cinemática inversa. Requiere modo 0 y estado READY (2).

        Args:
            angles (list[float]): ángulo objetivo por junta, EN RADIANES.
                Para xArm6 → 6 valores; para xArm7 → 7.
            speed (float): velocidad articular máxima, en rad/s (default 0.35).
            acc (float): aceleración articular máxima, en rad/s² (default 10.0).
            wait (bool): si True, bloquea hasta que el movimiento termina;
                si False, retorna apenas el comando es aceptado (default True).

        Returns:
            int: ret del driver. 0 = éxito.
        """
        request = MoveJoint.Request()
        request.angles = angles
        request.speed = speed
        request.acc = acc
        request.wait = wait
        future = self.set_servo_angle_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'set_servo_angle(angles={angles},speed={speed},acc={acc},wait={wait}) -> ret={response.ret}')
        return response.ret

    def set_position(self, pose, speed = 200.0, acc = 2000.0, wait=True):
        """Mueve el brazo en espacio cartesiano (Cartesian space).

        Especifica la pose del efector final (TCP); el firmware resuelve la
        cinemática inversa. Con motion_type=0 (default) el movimiento es lineal:
        si la línea recta no es alcanzable, falla (error C40). Requiere modo 0
        y estado READY (2).

        Args:
            pose (list[float]): pose objetivo del TCP como [x, y, z, roll, pitch, yaw].
                OJO CON LAS UNIDADES: x, y, z en MILÍMETROS; roll, pitch, yaw
                en RADIANES.
            speed (float): velocidad lineal máxima del TCP, en mm/s (default 200.0).
            acc (float): aceleración lineal máxima del TCP, en mm/s² (default 2000.0).
            wait (bool): si True, bloquea hasta que el movimiento termina;
                si False, retorna apenas el comando es aceptado (default True).

        Returns:
            int: ret del driver. 0 = éxito.
        """
        request = MoveCartesian.Request()
        request.pose = pose
        request.speed = speed
        request.acc = acc
        request.wait = wait
        future = self.set_position_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'set_position(pose={pose},speed={speed},acc={acc},wait={wait}) -> ret={response.ret}')
        return response.ret
        


def main():
    rclpy.init()
    node = FredArm()
    ret_motion_enable = node.motion_enable(1, 8)
    ret_set_mode = node.set_mode(0)
    ret_set_state = node.set_state(0)
    ret_set_servo_angle = node.set_servo_angle([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    node.get_logger().info(f'resultado: motion_enable={ret_motion_enable}, set_mode={ret_set_mode}, set_state={ret_set_state}, set_servo_angle={ret_set_servo_angle}')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
