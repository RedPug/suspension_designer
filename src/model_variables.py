from typing import Any
from uuid import UUID, uuid4

from PySide6.QtCore import (QObject, Signal)

from src.properties import DropdownPropertyType, NumberPropertyType, Property, StringPropertyType
from src.structures import EditorNode

class ModelVariableElement(QObject):
    did_change = Signal()

    def __init__(self, model_variable:'ModelVariable'):
        super().__init__()

        self._variable: ModelVariable = model_variable
        self._variable.did_change.connect(self.did_change.emit)

    @property
    def name(self):
        return self._variable.name
    
    @name.setter
    def name(self, value):
        self._variable.name = value
    
    @property
    def id(self):
        return self._variable.id
    
    @property
    def variable(self):
        return self._variable
    
    @variable.setter
    def variable(self, value):
        if not isinstance(value, ModelVariable):
            raise ValueError("variable must be an instance of ModelVariable")
        if self._variable is not None:
            self._variable.did_change.disconnect(self.did_change.emit)

        self._variable = value
        self._variable.did_change.connect(self.did_change.emit)
        self.did_change.emit()

    def fill_references(self, nodes: list[EditorNode]):
        self._variable.fill_references(nodes)

    def get_subselections(self) -> list[EditorNode]:
        if hasattr(self._variable, 'get_subselections'):
            return self._variable.get_subselections()
        return []
    
    def get_property_list(self) -> dict[str, list[Property]]:
        return {
            "Info": [
                Property("ID",
                    get=lambda _: self.id,
                    type=StringPropertyType()
                ),
                Property("Name",
                    get=lambda _: self.name,
                    set=lambda name, _: setattr(self, 'name', name),
                    type=StringPropertyType()
                ),
                Property("Type",
                    get=lambda _: self._variable.__class__,
                    set=lambda v, _: setattr(self, 'variable', v(name=self._variable.name, id=self._variable.id)),
                    type=DropdownPropertyType(
                        options_callback=lambda _: {"Displacement": DisplacementVariable, "Distance": DistanceVariable}
                    )
                )
            ]
        } | self._variable.get_property_list()
    
    def to_dict(self) -> dict[str, str]:
        return self._variable.to_dict()
    
    @staticmethod
    def from_dict(data) -> 'ModelVariableElement':
        var = ModelVariable.from_dict(data)
        return ModelVariableElement(model_variable=var)


class ModelVariable(QObject):
    did_change = Signal()

    def __init__(self, name: str, *, id: UUID = None):
        super().__init__()

        self._name = name
        self.id = id if id is not None else uuid4()  # Unique identifier for the quantity

    @property
    def name(self):
        return self._name
    
    @name.setter
    def name(self, value):
        self._name = value
        self.did_change.emit()
    
    def evaluate(self) -> float:
        pass

    def prescribe(self, value: float):
        pass

    def get_property_list(self):
        return {}
    
    def fill_references(self, nodes: list[EditorNode]):
        pass
    
    def to_dict(self):
        return {
            "name": self.name,
            "id": str(self.id)
        }
    
    @staticmethod
    def from_dict(data):
        type = data.get("type")
        if type is None:
            return None
        if type == "displacement":
            quantity = DisplacementVariable.from_dict(data)
            return quantity
        elif type == "distance":
            quantity = DistanceVariable.from_dict(data)
            return quantity

class DisplacementVariable(ModelVariable):
    def __init__(self, name:str, axis_x=0.0, axis_y=0.0, axis_z=0.0, *, id: UUID = None):
        super().__init__(name=name, id=id)

        self._axis_x = float(axis_x)
        self._axis_y = float(axis_y)
        self._axis_z = float(axis_z)

        self._node = None

    @property
    def node(self):
        return self._node
    
    @node.setter
    def node(self, value):
        self._node = value
        self.did_change.emit()

    @property
    def axis_x(self):
        return self._axis_x
    
    @axis_x.setter
    def axis_x(self, value):
        self._axis_x = float(value)
        self.did_change.emit()

    @property
    def axis_y(self):
        return self._axis_y
    
    @axis_y.setter
    def axis_y(self, value):
        self._axis_y = float(value)
        self.did_change.emit()

    @property
    def axis_z(self):
        return self._axis_z
    
    @axis_z.setter
    def axis_z(self, value):
        self._axis_z = float(value)
        self.did_change.emit()

    def get_property_list(self) -> dict[str, list[Property]]:
        return super().get_property_list() | {
            "Transform":[
                Property("Node",
                    get=lambda _: self.node,
                    set=lambda node, _: setattr(self, 'node', node),
                    type=DropdownPropertyType(
                        options_callback = lambda scene: {"No Selection": None} | {node.name: node for node in scene.nodes}
                    )
                ),
                Property("Axis X",
                    get = lambda _: self.axis_x,
                    set = lambda v, _: setattr(self, 'axis_x', v),
                    type=NumberPropertyType(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
                ),
                Property("Axis Y",
                    get = lambda _: self.axis_y,
                    set = lambda v, _: setattr(self, 'axis_y', v),
                    type=NumberPropertyType(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
                ),
                Property("Axis Z",
                    get = lambda _: self.axis_z,
                    set = lambda v, _: setattr(self, 'axis_z', v),
                    type=NumberPropertyType(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
                )
            ]
        }
    
    def get_subselections(self) -> list[EditorNode]:
        return [self.node] if self.node is not None else []
    
    def to_dict(self):
        return super().to_dict() | {
            "type": "displacement",
            "axis_x": self.axis_x,
            "axis_y": self.axis_y,
            "axis_z": self.axis_z,
            "node_id": str(self.node.id) if self.node is not None else ""
        }
    
    @staticmethod
    def from_dict(data):
        quantity = DisplacementVariable(
            name = data.get("name",""),
            id = UUID(data.get("id")) if data.get("id") else None,
            axis_x = data.get("axis_x"),
            axis_y = data.get("axis_y"),
            axis_z = data.get("axis_z"),
        )

        if data.get("node_id") != "":
            quantity.node_id = UUID(data.get("node_id"))
        else:
            quantity.node_id = None

        return quantity
    
    def fill_references(self, id_to_element: dict[UUID, Any]):
        if self.node_id is not None:
            self.node: EditorNode = id_to_element.get(self.node_id)
            if self.node is None and self.node_id != None:
                print(f"Warning: Node not found for model quantity {self.name}")
        else:
            print(f"Warning: Node ID is None for model quantity {self.name}")
            self.node = None
        del self.node_id
    
class DistanceVariable(ModelVariable):
    def __init__(self, name:str, node_a:EditorNode = None, node_b:EditorNode = None, *, id: UUID = None):
        super().__init__(name=name, id=id)

        self._node_a = node_a
        self._node_b = node_b

    @property
    def node_a(self):
        return self._node_a
    
    @node_a.setter
    def node_a(self, value):
        self._node_a = value
        self.did_change.emit()

    @property
    def node_b(self):
        return self._node_b
    
    @node_b.setter
    def node_b(self, value):
        self._node_b = value
        self.did_change.emit()


    def get_property_list(self) -> dict[str, list[Property]]:
        return super().get_property_list() | {
            "Transform":[
                Property("Node A",
                    get=lambda _: self.node_a,
                    set=lambda node, _: setattr(self, 'node_a', node),
                    type=DropdownPropertyType(
                        options_callback = lambda scene: {"No Selection": None} | {node.name: node for node in scene.nodes if node != self.node_b}
                    )
                ),
                Property("Node B",
                    get=lambda _: self.node_b,
                    set=lambda node, _: setattr(self, 'node_b', node),
                    type=DropdownPropertyType(
                        options_callback = lambda scene: {"No Selection": None} | {node.name: node for node in scene.nodes if node != self.node_a}
                    )
                ),
            ]
        }
    
    def get_subselections(self) -> list[EditorNode]:
        return [self.node_a, self.node_b]
    
    def to_dict(self):
        return super().to_dict() | {
            "type": "distance",
            "node_a_id": str(self.node_a.id),
            "node_b_id": str(self.node_b.id)
        }
    
    @staticmethod
    def from_dict(data):
        quantity = DistanceVariable(
            name = data.get("name",""),
            id = UUID(data.get("id")) if data.get("id") else None,
        )

        if data.get("node_a_id") is not None:
            quantity.node_a_id = UUID(data.get("node_a_id"))
        else:
            quantity.node_a_id = None

        if data.get("node_b_id") is not None:
            quantity.node_b_id = UUID(data.get("node_b_id"))
        else:
            quantity.node_b_id = None

        return quantity
    
    def fill_references(self, id_to_element: dict[UUID, any]):
        if not hasattr(self, 'node_a_id') or not hasattr(self, 'node_b_id'):
            print("Warning: DistanceVariable does not have 'node_a_id' or 'node_b_id' attribute. Cannot fill references.")
            return

        if self.node_a_id is not None:
            self.node_a: EditorNode = id_to_element.get(self.node_a_id)
            if self.node_a is None and self.node_a_id != None:
                print(f"Warning: Node A not found for model quantity {self.name}")
        else:
            print(f"Warning: Node A ID is None for model quantity {self.name}")
            self.node_a = None

        if self.node_b_id is not None:
            self.node_b: EditorNode = id_to_element.get(self.node_b_id)
            if self.node_b is None and self.node_b_id != None:
                print(f"Warning: Node B not found for model quantity {self.name}")
        else:
            print(f"Warning: Node B ID is None for model quantity {self.name}")
            self.node_b = None

        del self.node_a_id
        del self.node_b_id