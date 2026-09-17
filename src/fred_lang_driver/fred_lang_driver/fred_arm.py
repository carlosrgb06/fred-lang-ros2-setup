import rclpy
import math
from rclpy.node import Node
from .fred_arm_error import FredArmError
from xarm_msgs.srv import SetInt16ById, SetInt16, MoveJoint, MoveCartesian, MoveHome, Call
from xarm_msgs.msg import RobotMsg



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
        self.clean_error_client = self._make_client(Call, '/xarm/clean_error')
        self.move_gohome_client = self._make_client(MoveHome, '/xarm/move_gohome')

        self._last_state = None # Es None cuando no se ha leido el topico
        self.robot_states_sub = self.create_subscription(RobotMsg, '/xarm/robot_states', self._robot_states_cb,10)

 # Helpers
    def resumen_estado(self):
        s = self._last_state
        if s is None:
            return 'sin estado (nunca se leyo /xarm/robot_states)'
        return f'state={s.state}, err={s.err}, servos_ok={self.servos_ok()}'
    
    def hay_error(self):
        """Verifica si el brazo reporta algun error a traves del campo err en /xarm/robot_states"""

        if self._last_state is None:
            return False
        return self._last_state.err != 0
    
    def servos_ok(self, num_joints=6):
        """ Verifica si los servos estan habilitados a traves del bitmask mt_able en /xarm/robot_states.
        
        Args:
            num_joints (int): numero de articulaciones del brazo (default= 6)
        
        Returns:
            bool: True si todos los servos están habilitados, False de lo contrario.
        """
        if self._last_state is None:
            return False
        mascara = (1 << num_joints) -1   # 6 juntas -> 0b111111 = 63
        return (self._last_state.mt_able & mascara) == mascara

    def estado_ok(self, timeout = 10.0):
        """Bloquea hasta que el brazo este listo para continuar. err=0 y todos los servos habilitados por servos_ok().
        
        Args:
            timeout (float): tiempo maximo a esperar en segundos (default=10.0)
        Returns:
            bool: True si el brazo esta listo para moverse, False si se agoto el tiempo o hay un error con los campos mencionados
        """
        inicio = self.get_clock().now()
        while rclpy.ok():
            rclpy.spin_once(self,timeout_sec=0.1)
            if self._last_state is None:
                continue
            if self.hay_error():
                self.get_logger().error(f'Error en el brazo: {self._last_state.err}')
                return False
            if self._last_state.state == 2 and self.servos_ok():
                return True
            transcurrido = (self.get_clock().now() - inicio).nanoseconds / 1e9
            if transcurrido > timeout:
                self.get_logger().error(f'Timeout alcanzado. Ultimo estado: {self._last_state}')
                return False
        return False

    def get_angulos(self):
        """Devuelve los ángulos articulares actuales (rad), o None si no hay estado aún."""
        if self._last_state is None:
            return None
        return list(self._last_state.angle)

    def verificar_listo(self):
        """Verifica que el brazo este listo para moverse checando si no hay errores, si el state del brazo es 2 o si no se corrio la secuencia de arranque encapsulada en preparar()
        
        Raises:
            FredArmError: Si no se corrio la funcion preparar() previo a esta
            FredArmError: Si el brazo tiene un error
            FredArmError: Si el brazo no esta en READY/SLEEPING (state=2)
        """
        rclpy.spin_once(self, timeout_sec=0.2)
        if self._last_state is None:
            raise FredArmError('sin estado del brazo. ¿Corriste preparar()?, _last_state = none')
        if self.hay_error():
            raise FredArmError(f'el brazo esta en error: {self.resumen_estado()}')
        if self._last_state.state != 2:
            raise FredArmError(f'el brazo no esta READY: {self.resumen_estado()}')
        
 # Clientes de servicios directos (Capa 1)

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
        request.id = int(id)
        request.data = int(enable)
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

        Nota: los modos leidos en /xarm/robot_states
        # mode of robot:
            #	0 for POSITION mode.(position control by xarm controller box, execute api standard commands)
            #	1 for SERVOJ mode. (Immediate execution towards received joint space target, like a step response)
            #	2 for TEACHING_JOINT mode. (Gravity compensated mode, easy for teaching)
        """
        request = SetInt16.Request()
        request.data = int(mode)
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
            # state of robot:
            #	1: RUNNING, executing motion command.
            #	2: SLEEPING, not in execution, but ready to move.
            #	3: PAUSED, paused in the middle of unfinished motion.
            #	4: STOPPED, not ready for any motion commands.
            #	5: CONFIG_CHANGED, system configuration or mode changed, not ready for motion commands.
        """
        request = SetInt16.Request()
        request.data = int(state)
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
        request.angles = [float(v) for v in angles]
        request.speed = float(speed)
        request.acc = float(acc)
        request.wait = bool(wait)
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
        request.pose = [float (v) for v in pose]
        request.speed = float(speed)
        request.acc = float(acc)
        request.wait = bool(wait)
        future = self.set_position_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'set_position(pose={pose},speed={speed},acc={acc},wait={wait}) -> ret={response.ret}')
        return response.ret

    def clean_error(self):
        """Limpia el codigo de error del xarm
        
        Tras limpiar, hay que volver a set_state(0) para reactivar el movimiento

        Returns:
            int: ret del driver. 0 = exito
        """
        request = Call.Request()
        future = self.clean_error_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'clean_error() -> ret={response.ret}')
        return response.ret

    def move_gohome(self, speed = 0.35, acc = 10.0, wait=True):
        """Mueve el brazo a la posición de reposo (home). Establecida por ufactory en fábrica, no es configurable por el usuario.
        
        Args:
            speed (float): velocidad articular, en rad/s (default 0.35).
            acc (float): aceleración articular, en rad/s² (default 10.0).
            wait (bool): si True, bloquea hasta terminar (default True).

        Returns:
            int: ret del driver. 0 = éxito.
        """
        request = MoveHome.Request()
        request.speed = float(speed)
        request.acc = float(acc)
        request.wait = bool(wait)
        future = self.move_gohome_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'move_gohome(speed={speed}, acc={acc}, wait={wait}) -> ret={response.ret}')
        return response.ret

 # Callbacks 
    def _robot_states_cb(self,msg):

        self._last_state = msg

 # Funciones de alto nivel (Capa 3)

    def preparar(self, enable=1, id=8, mode=0, state=0):
        """Secuencia de arranque del brazo

        Args:
            enable (int): 1 = habilitar, 0 = deshabilitar. default(enable=1)
            id (int): servo objetivo. 1-7 para un eje individual,
                8 = todos los ejes a la vez (default).

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

            state (int): estado a fijar (OJO: los valores que se FIJAN no son
                los mismos que se LEEN en /xarm/robot_states).
                0 = STANDBY: pone el brazo listo en el modo actual y limpia
                    errores. El feedback pasará a 2 (READY) automáticamente.
                3 = PAUSED: pausa la ejecución; se reanuda con set_state(0).
                4 = STOP: termina toda ejecución de inmediato; no acepta
                    comandos nuevos hasta volver a STANDBY (0).
            
            Nota: los estados LEÍDOS en /xarm/robot_states usan otra tabla:
            # state of robot:
            #	1: RUNNING, executing motion command.
            #	2: SLEEPING, not in execution, but ready to move.
            #	3: PAUSED, paused in the middle of unfinished motion.
            #	4: STOPPED, not ready for any motion commands.
            #	5: CONFIG_CHANGED, system configuration or mode changed, not ready for motion commands.

        Returns:
            None. Si el arranque tiene exito, retorna sin mas; la ausencia de
            excepcion ES la señal de exito.

        Raises:
            FredArmError: si motion_enable, set_mode o set_state devuelven un ret
            invalido, o si el brazo no llega a READY tras el arranque.
        """
        if enable not in (0, 1):
            raise FredArmError(f'preparar() espera enable 0 o 1, recibio {enable!r}')
        ret = self.motion_enable(enable, id)
        #REVISAR EN HARDWARE REAL
        if ret != 0 and ret != 3: # ret=3 es un "timeout cosmético" contra el firmware sim, pero los servos SÍ se habilitan; verificar mt_able en /xarm/robot_states.
            raise FredArmError(f'motion_enable fallo con ret={ret}')
        ret = self.set_mode(mode)
        if ret != 0:
            raise FredArmError(f'set_mode fallo con ret={ret}')
        ret = self.set_state(state)
        if ret != 0:
            raise FredArmError(f'set_state fallo con ret={ret}')
        if not self.estado_ok():
            raise FredArmError(f'preparar() completo los servicios pero el brazo no llego a READY/SLEEPING: {self.resumen_estado()}')

    def recuperar(self):
        """Funcion que recupera el brazo de un estado de error: limpia el error re-ejecuta el arranque completo.
        
        Returns:
            None. Si la recuperación tiene exito, retorna sin mas; la ausencia de
            excepcion ES la señal de exito.
        Raises:
            FredArmError: si clean_error no devuelve un ret = 0
            
            FredArmError: si motion_enable, set_mode o set_state devuelven un ret
            invalido, o si el brazo no llega a READY tras el arranque.
        """
        ret = self.clean_error()
        if ret != 0:
            raise FredArmError(f'clean_error -> ret={ret}')
        self.preparar()

    def mover_a(self, x,y,z, roll=math.pi, pitch=0.0 ,yaw= 0.0,speed=200.0 ,acc=2000.0):
        """Funcion que encapsula el servicio de set_position en una primitiva de alto nivel
        
        Args:
            x(float o int) = posicion deseada en el eje x en mm (milimetros)
            y(float o int) = posicion deseada en el eje y en mm (milimetros)
            z(float o int) = posicion deseada en el eje z en mm (milimetros)
            roll(float o int) = orientacion deseada en el eje x en radianes default: roll = math.pi
            pitch(float o int) = orientacion deseada en el eje y en radianes default: pitch = 0
            yaw(float o int) = orientacion deseada en el eje z en radianes default: yaw = 0

            Los valores defaults para roll,pitch y yaw hacen que la orientacion predeterminada sea con el actuador viendo hacia abajo

            speed (float o int, positivos): velocidad lineal máxima del TCP, en mm/s (default 200.0).
            acc (float o int, positivos): aceleración lineal máxima del TCP, en mm/s² (default 2000.0).
        
        
        Returns:
            None. Si el movimiento tiene exito, retorna sin mas; la ausencia de
            excepcion ES la señal de exito.
        

        Raises:
            FredArmError: Si x,y,z,roll,pitch,yaw no son de tipo int o float
            FredArmError: Si speed o acc no son de tipo int o float, positivos
            FredArmError: Si no se corrio la funcion preparar() previo a esta (ver verificar_listo())
            FredArmError: Si el brazo tiene un error (ver verificar_listo())
            FredArmError: Si el brazo no esta en READY/SLEEPING (state=2) (ver verificar_listo())
            FredArmError: Si set_position ret->(!=0) 
            FredArmError: Si no se regresa a un estado de READY/SLEEPING state=(2) despues del movimiento
        
        """
        for valor in (x, y, z, roll, pitch, yaw):
            if not isinstance(valor, (int, float)):
                raise FredArmError(f'mover_a espera numeros, recibio {valor!r} ({type(valor).__name__})')
        for valor in (speed, acc):
            if not isinstance(valor, (int, float)):
                raise FredArmError(f'mover_a: speed/acc deben ser numeros, recibio {valor!r}')
            if valor <= 0:
                raise FredArmError(f'mover_a: speed/acc deben ser positivos, recibio {valor}')
            
        self.verificar_listo()

        pose = [x,y,z,roll,pitch,yaw]
        ret = self.set_position(pose,speed,acc,wait=True)
        if ret != 0:
            raise FredArmError(f'set_position fallo con ret={ret}')
        if not self.estado_ok():
            raise FredArmError(f'mover_a() completo los servicios pero el brazo no llego a READY/SLEEPING: {self.resumen_estado()}')

    def mover_servos_a(self, angulos,num_joints=6,speed=0.35,acc=10.0):
        """Funcion que encapsula el servicio set_servo_angle en una primitiva de alto nivel
        Args:
            num_joints (int): El numero de juntas que tiene el robot default(num_joints=6)
            angulos (lista): La lista con el angulo deseado para cada junta
            speed: velocidad en que las juntas se moveran (rad/s) default(speed=0.35)
            acc: aceleracion en que las juntas se moveran (rad/s^2) default(acc=10)
        Returns:
            None. Si el movimiento tiene exito, retorna sin mas; la ausencia de
            excepcion ES la señal de exito.
        Raises:
            FredArmError: Si num_joints no es de tipo int
            FredArmError: Si angulos no es de tipo list
            FredArmError: Si angulos no tiene la cantidad de argumentos correspondientes a num_joints
            FredArmError: Si speed o acc no son de tipo int o float, positivos
            FredArmError: Si no se corrio la funcion preparar() previo a esta (ver verificar_listo())
            FredArmError: Si el brazo tiene un error (ver verificar_listo())
            FredArmError: Si el brazo no esta en READY/SLEEPING (state=2) (ver verificar_listo())
            FredArmError: Si set_servo_angle ret->(!=0) 
            FredArmError: Si no se regresa a un estado de READY/SLEEPING state=(2) despues del movimiento
        """
        if not isinstance(num_joints,int):
            raise FredArmError(f'El numero de juntas (num_joints={num_joints}) debe ser entero (int) y coincidente con el modelo de xarm utilizado')
        if not isinstance(angulos,list):
            raise FredArmError(f'El argumento (angulos={angulos}) debe ser de tipo lista')
        if len(angulos) != num_joints:
            raise FredArmError(f'Los angulos en la lista (angulos={angulos}) debe coincidir con el numero de juntas (num_joints={num_joints})')
        for valor in angulos:
            if not isinstance(valor,(int,float)):
                raise FredArmError(f'Todos los valores en el argumento "angulos" debe ser de tipo int o float')
        for valor in (speed, acc):
            if not isinstance(valor, (int, float)):
                raise FredArmError(f'mover_servos_a: speed/acc deben ser numeros, recibio {valor!r}')
            if valor <= 0:
                raise FredArmError(f'mover_servos_a: speed/acc deben ser positivos, recibio {valor}')

        self.verificar_listo()

        ret = self.set_servo_angle(angulos,speed,acc,wait=True)
        if ret != 0:
            raise FredArmError(f'set_servo_angle fallo con ret={ret}')
        if not self.estado_ok():
            raise FredArmError(f'mover_servos_a() completo los servicios pero el brazo no llego a READY/SLEEPING: {self.resumen_estado()}')

    def home(self):
        """Funcion que encapsula el servicio move_gohome. Primitiva de alto nivel en capa 3 que manda al robot a sus coordenadas bases impuestas por el fabricante
        
        Raises:
            FredArmError: Si no se corrio la funcion preparar() previo a esta (ver verificar_listo())
            FredArmError: Si el brazo tiene un error (ver verificar_listo())
            FredArmError: Si el brazo no esta en READY/SLEEPING (state=2) (ver verificar_listo())
            FredArmError: Si move_gohome ret->(!=0) 
            FredArmError: Si no se regresa a un estado de READY/SLEEPING state=(2) despues del movimiento
        """
        self.verificar_listo()
        ret = self.move_gohome()
        if ret !=0:
            raise FredArmError(f'move_gohome fallo con ret={ret}')
        if not self.estado_ok():
            raise FredArmError(f'home() completo los servicios pero el brazo no llego a READY/SLEEPING: {self.resumen_estado()}')  

           
def main():
    rclpy.init()
    arm = FredArm()
    try:
        # 1. preparar() — arranque completo, deja el brazo en READY
        arm.get_logger().info('=== preparar() ===')
        arm.preparar()
        arm.get_logger().info(f'Ángulos tras preparar: {arm.get_angulos()}')

        # 2. mover_servos_a() — movimiento articular a una postura conocida (cerca de home)
        arm.get_logger().info('=== mover_servos_a() ===')
        arm.mover_servos_a([0.0, -0.2, 0.0, 0.2, 0.0, 0.0])
        arm.get_logger().info(f'Ángulos tras mover_servos_a: {arm.get_angulos()}')

        # 3. mover_a() — movimiento cartesiano (efector hacia abajo por defecto)
        arm.get_logger().info('=== mover_a() ===')
        arm.mover_a(x=206, y=0, z=150.5)
        arm.get_logger().info(f'Ángulos tras mover_a: {arm.get_angulos()}')

        # 4. home() — regreso al home de fábrica
        arm.get_logger().info('=== home() ===')
        arm.home()
        arm.get_logger().info(f'Ángulos tras home: {arm.get_angulos()}')

        # 5. recuperar() sobre brazo sano — prueba de idempotencia (no hay error que limpiar)
        arm.get_logger().info('=== recuperar() (brazo sano) ===')
        arm.recuperar()
        arm.get_logger().info(f'Ángulos tras recuperar: {arm.get_angulos()}')

        arm.get_logger().info('=== Todas las primitivas de Capa 3 funcionaron ===')

    except FredArmError as e:
        arm.get_logger().error(f'Una primitiva falló: {e}')
    finally:
        arm.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
