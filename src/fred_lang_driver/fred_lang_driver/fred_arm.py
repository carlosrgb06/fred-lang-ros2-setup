import rclpy
from rclpy.node import Node
from xarm_msgs.srv import SetInt16ById


class FredArm(Node):
    def __init__(self):
        super().__init__('fred_arm_node')
        self.motion_enable_client = self.create_client(SetInt16ById, '/xarm/motion_enable')
        if not self.motion_enable_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('/xarm/motion_enable service not available, shutting down node')
            raise RuntimeError('xarm_api driver not running')

    def motion_enable(self, enable, id=8):
        request = SetInt16ById.Request()
        request.id = id
        request.data = enable
        future = self.motion_enable_client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        self.get_logger().info(f'motion_enable(enable={enable}, id={id}) -> ret={response.ret}')
        return response.ret


def main():
    rclpy.init()
    node = FredArm()
    ret = node.motion_enable(1, 8)
    node.get_logger().info(f'resultado: {ret}')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
