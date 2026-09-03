import rclpy
from rclpy.node import Node
from example_interfaces.srv import AddTwoInts

class SumadorNode(Node):
    def __init__(self):
        super().__init__('sumador_node')
        self.create_service(AddTwoInts,'sumar',self.sumar_callback)
        # aquí van los servicios, la conexión al SDK, etc.

    def sumar_callback(self,request,response):
        response.sum = request.a + request.b
        return response

def main():
    rclpy.init()
    node = SumadorNode()
    rclpy.spin(node)     # deja al nodo vivo, escuchando llamadas
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()