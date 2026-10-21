from typing import Optional

from uuid import UUID

from PySide6.QtCore import (QObject, Signal)

import numpy as np

# from src.solver import SolverState, solve_system, SolverResult
from suspension_designer.editor.commands import CommandFactory, LocalModifyElementCommand, LocalModifyElementCommandFactory, NonLocalModifyElementCommand, NonLocalModifyElementCommandFactory
from suspension_designer.elements.core import EditorElement
from suspension_designer.user_interface.properties import DropdownPropertyEditorFactory, GroupPropertyEditorFactory, NumberPropertyEditorFactory, Property, StringPropertyEditorFactory
# from src.scene import SceneState
from suspension_designer.user_interface.selection import Selectable



class EditorNode(EditorElement):

    def __init__(self, name: str, *, world_position: np.ndarray, id: UUID = None):
        super().__init__(name, id=id)

        self._world_position = world_position

    @property
    def world_position(self):
        return self._world_position
    
    @world_position.setter
    def world_position(self, value):
        self.set_world_position(value)

    def set_world_position(self, value, ignore_direction: Optional[np.ndarray] = None):
        self._world_position = value
        self.did_change.emit()

    @property
    def x(self):
        return self.world_position[0]

    @x.setter
    def x(self, x):
        self.set_world_position(np.array([x, self.world_position[1], self.world_position[2]]), ignore_direction=np.array([1, 0, 0]))
    @property
    def y(self):
        return self.world_position[1]
    
    @y.setter
    def y(self, y):
        self.set_world_position(np.array([self.world_position[0], y, self.world_position[2]]), ignore_direction=np.array([0, 1, 0]))
    @property
    def z(self):
        return self.world_position[2]
    
    @z.setter
    def z(self, z):
        self.set_world_position(np.array([self.world_position[0], self.world_position[1], z]), ignore_direction=np.array([0, 0, 1]))
    
    def fill_references(self, id_to_element: dict[UUID, EditorElement]):
        pass
    
    def get_property_list(self):
        return {
            "Info":[
                Property("ID",
                    get=lambda _: self.id,
                    prop_editor=StringPropertyEditorFactory()
                ),
                Property("Name",
                    get=lambda _: self.name,
                    set=LocalModifyElementCommandFactory(element_id=self.id, property_name='name'),
                    prop_editor=StringPropertyEditorFactory()
                )
            ],
            "Transform":[
                Property("X",
                    get=lambda _: self.world_position[0],
                    set=NonLocalModifyElementCommandFactory(element_id=self.id, property_name='x'),
                    prop_editor=NumberPropertyEditorFactory(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
                ),
                Property("Y",
                    get=lambda _: self.world_position[1],
                    set=NonLocalModifyElementCommandFactory(element_id=self.id, property_name='y'),
                    prop_editor=NumberPropertyEditorFactory(multiplier=1e-3, step=1.0, decimals=2,  suffix=" mm")
                ),
                Property("Z",
                    get=lambda _: self.world_position[2],
                    set=NonLocalModifyElementCommandFactory(element_id=self.id, property_name='z'),
                    prop_editor=NumberPropertyEditorFactory(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
                )
            ]
        }

    def __eq__(self, other):
        if not isinstance(other, EditorNode):
            return False
        return self._id == other._id
    
    def __str__(self):
        return f"EditorNode(name='{self._name}', world_position={self._world_position.tolist()})"

    def __repr__(self):
        return f"EditorNode(name='{self._name}', id={self._id}, world_position={self._world_position.tolist()})"

    def to_dict(self):
        return {
            'id': str(self._id),
            'name': self._name,
            'world_position': self._world_position.tolist()
        }

    @staticmethod
    def from_dict(data: dict) -> 'EditorNode':
        node = EditorNode(
            name=data['name'],
            world_position=np.array(data['world_position'], dtype=float),
            id=UUID(data['id'])
        )
        return node

class NodeGroup(EditorElement):

    def __init__(self, name: str, *, id:UUID = None, nodes: list[EditorNode]):
        super().__init__(name, id=id)
        self._nodes = nodes

    @property
    def nodes(self):
        return self._nodes
    
    @nodes.setter
    def nodes(self, value):
        self._nodes = value
        # print(f"Node group {self.name} nodes updated to {[node.name for node in self._nodes]}")
        self.did_change.emit()

    def fill_references(self, id_to_element: dict[UUID, EditorNode]):
        if not hasattr(self, 'node_ids'):
            print("Warning: NodeGroup does not have 'node_ids' attribute. Cannot fill references.")
            return
        
        self.nodes = [id_to_element.get(node_id) for node_id in self.node_ids]

        for node in self.nodes:
            if node is None:
                print(f"Warning: Node not found for group {self.name}.")

        del self.node_ids  # Clean up the temporary attribute

    def get_property_list(self) -> dict[str, list[Property]]:
        return {
            "Info": [
                Property("ID",
                    get=lambda _: self.id,
                    prop_editor=StringPropertyEditorFactory()
                ),
                Property("Name",
                    get=lambda _: self.name,
                    set=LocalModifyElementCommandFactory(element_id=self.id, property_name='name'),
                    prop_editor=StringPropertyEditorFactory()
                ),
                Property("Contains",
                    get = lambda _: self.nodes,
                    set = LocalModifyElementCommandFactory(element_id=self.id, property_name='nodes'),
                    prop_editor = GroupPropertyEditorFactory(all_elements_callback = lambda doc: doc.scene.nodes)
                ),
            ]
        }
    
    def __str__(self):
        return f"NodeGroup(name='{self._name}', nodes={[node.name for node in self._nodes]})"
    
    def __repr__(self):
        return f"NodeGroup(name='{self._name}', id={self.id}, nodes={[node.name for node in self._nodes]})"

    def to_dict(self):
        return {
            'name': self.name,
            'id': str(self.id),
            'node_ids': [str(node.id) for node in self.nodes]
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'NodeGroup':
        node_ids = [UUID(node_id) for node_id in data['node_ids']]
        group = NodeGroup(name=data['name'], id=UUID(data['id']), nodes=[])
        group.node_ids = node_ids  # Store the IDs temporarily
        return group