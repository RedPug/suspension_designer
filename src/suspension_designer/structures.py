from enum import Enum, StrEnum, auto
from time import perf_counter
from typing import Any, Callable, List, Literal, Optional, Union
from uuid import UUID, uuid4

from PySide6.QtCore import (QObject, Signal)

import numpy as np

# from src.solver import SolverState, solve_system, SolverResult
from suspension_designer.properties import DropdownPropertyType, GroupPropertyType, NumberPropertyType, Property, StringPropertyType
# from src.scene import SceneState
from suspension_designer.selection import Selectable


class EditorNode(Selectable):

    def __init__(self, name: str, *, world_position: np.ndarray, id: UUID = None):
        super().__init__(name, id=id)

        self._world_position = world_position
        self._locked_plane: Optional[ReferencePlane] = None  # The plane to which this node is locked, if any

    @property
    def world_position(self):
        return self._world_position
    
    @world_position.setter
    def world_position(self, value):
        self.set_world_position(value)

    def set_world_position(self, value, ignore_direction: Optional[np.ndarray] = None):
        if self._locked_plane is not None:
            value = self._locked_plane.constrain_point(value, ignore_direction=ignore_direction)

        self._world_position = value
        self.did_change.emit()
    
    def set_x(self, x):
        self.set_world_position(np.array([x, self.world_position[1], self.world_position[2]]), ignore_direction=np.array([1, 0, 0]))

    def set_y(self, y):
        self.set_world_position(np.array([self.world_position[0], y, self.world_position[2]]), ignore_direction=np.array([0, 1, 0]))

    def set_z(self, z):
        self.set_world_position(np.array([self.world_position[0], self.world_position[1], z]), ignore_direction=np.array([0, 0, 1]))

    @property
    def locked_plane(self):
        return self._locked_plane

    @locked_plane.setter
    def locked_plane(self, value):
        if self._locked_plane is not None:
            self._locked_plane.did_change.disconnect(self._on_locked_plane_changed)

        self._locked_plane = value
        if self._locked_plane is not None:
            self._locked_plane.did_change.connect(self._on_locked_plane_changed)
        self.world_position = self.world_position  # Re-apply the constraint to ensure the position is valid
    
    def fill_references(self, id_to_element: dict[UUID, Any]):
        if not hasattr(self, '_locked_plane_id'):
            print("Warning: EditorNode does not have '_locked_plane_id' attribute. Cannot fill references.")
            return

        self.locked_plane = id_to_element.get(self._locked_plane_id)
        if self.locked_plane is None and self._locked_plane_id is not None:
            print(f"Warning: Locked plane not found for node {self.name}.")

        del self._locked_plane_id  # Clean up the temporary attribute
    
    def _on_locked_plane_changed(self):
        # When the locked plane changes, re-apply the constraint to the current world position
        self.world_position = self.world_position  # This will trigger the constraint logic in set_world_position
    
    def set_plane_from_name(self, name: str, scene):
        plane = next((p for p in scene.reference_planes if p.name == name), None)
        self.locked_plane = plane
    
    def get_property_list(self):
        return {
            "Info":[
                Property("ID",
                    get=lambda _: self.id,
                    type=StringPropertyType()
                ),
                Property("Name",
                    get=lambda _: self.name,
                    set=lambda name, _: setattr(self, 'name', name),
                    type=StringPropertyType()
                ),
                Property("Constrainted to",
                    get=lambda _: self.locked_plane,
                    set=lambda plane, _: setattr(self, 'locked_plane', plane),
                    type=DropdownPropertyType(
                        options_callback = lambda scene: {"No Selection": None} | {plane.name: plane for plane in scene.reference_planes}
                    )
                ),
            ],
            "Transform":[
                Property("X",
                    get=lambda _: self.world_position[0],
                    set=lambda x, _: self.set_x(x),
                    type=NumberPropertyType(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
                ),
                Property("Y",
                    get=lambda _: self.world_position[1],
                    set=lambda y, _: self.set_y(y),
                    type=NumberPropertyType(multiplier=1e-3, step=1.0, decimals=2,  suffix=" mm")
                ),
                Property("Z",
                    get=lambda _: self.world_position[2],
                    set=lambda z, _: self.set_z(z),
                    type=NumberPropertyType(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
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
        return f"EditorNode(name='{self._name}', id={self._id}, world_position={self._world_position.tolist()}, locked_plane_id={self._locked_plane.id if self._locked_plane else None})"

    def to_dict(self):
        return {
            'id': str(self._id),
            'name': self._name,
            'world_position': self._world_position.tolist(),
            'locked_plane_id': str(self._locked_plane.id) if self._locked_plane is not None else None
        }

    @staticmethod
    def from_dict(data: dict) -> 'EditorNode':
        node = EditorNode(
            name=data['name'],
            world_position=np.array(data['world_position'], dtype=float),
            id=UUID(data['id'])
        )
        node._locked_plane_id = UUID(data['locked_plane_id']) if data['locked_plane_id'] is not None else None
        return node

class ReferencePlane(Selectable):
    class Mode(StrEnum):
        CONTAINING = auto()
        PERPENDICULAR = auto()

    def __init__(self, name: str = "Unnamed", *, id: UUID = None, mode: 'ReferencePlane.Mode', p0: EditorNode = None, p1: EditorNode = None, p2: EditorNode = None):
        super().__init__(name, id=id)

        self._mode = mode
        self._p0 = p0
        self._p1 = p1
        self._p2 = p2

        self._rebuild()

    def _rebuild(self):
        if self.p0 is None or self._p1 is None or self._p2 is None:
            self._point = None
            self._normal = None
            return
        
        if self.mode == ReferencePlane.Mode.CONTAINING:
            # Recreate a plane containing the three points
            v1 = self._p1.world_position - self._p0.world_position
            v2 = self._p2.world_position - self._p0.world_position
            normal = np.cross(v1, v2)
            normal /= np.linalg.norm(normal)
            point = self._p0.world_position
        elif self.mode == ReferencePlane.Mode.PERPENDICULAR:
            # Recreate a plane perpendicular to the vector from p0 to p1, passing through p2
            v = self._p1.world_position - self._p0.world_position
            normal = v / np.linalg.norm(v)
            point = self._p2.world_position
        else:
            print(f"Unknown mode: {self.mode}")
            raise ValueError("Invalid mode. Must be 'containing' or 'perpendicular'.")
        
        self._point = point
        self._normal = normal / np.linalg.norm(normal)

        self.did_change.emit()

    @property
    def point(self):
        return self._point

    @property
    def normal(self):
        return self._normal
    
    @property
    def p0(self):
        return self._p0
    
    @p0.setter
    def p0(self, value):
        self._p0 = value
        self._rebuild()

    @property
    def p1(self):
        return self._p1

    @p1.setter
    def p1(self, value):
        self._p1 = value
        self._rebuild()

    @property
    def p2(self):
        return self._p2

    @p2.setter
    def p2(self, value):
        self._p2 = value
        self._rebuild()

    @property
    def mode(self):
        return self._mode
    
    @mode.setter
    def mode(self, value):
        if type(value) is not ReferencePlane.Mode:
            raise ValueError("Invalid mode. Must be ReferencePlane.Mode.")
        self._mode = value
        self._rebuild()

    def update(self, other: 'ReferencePlane'):
        self._p0 = other._p0
        self._p1 = other._p1
        self._p2 = other._p2
        self._name = other._name
        self.id = other.id
        self._mode = other._mode
        self._rebuild()

    def constrain_point(self, point: np.ndarray, ignore_direction: np.ndarray = None) -> np.ndarray:
        if self._point is None or self._normal is None:
            return point

        # Project the point onto the plane
        d = np.dot(point - self.point, self.normal)

        if ignore_direction is None:
            return point - d * self.normal
        
        ignore_direction = ignore_direction / np.linalg.norm(ignore_direction)
        # around 26 degrees tolerance to say it's too close to the normal.
        if abs(np.dot(ignore_direction, self.normal)) > 0.90:
            return point - d * self.normal
        
        # print(f"Constraining point {point} to plane with normal {self.normal} while ignoring direction {ignore_direction}")

        A = point
        center = self.point

        n1 = self.normal
        n1 = n1 / np.linalg.norm(n1)

        n2 = ignore_direction
        n2 = n2 / np.linalg.norm(n2)

        # Direction of the intersection line
        v = np.cross(n1, n2)
        if np.dot(v, v) < 1e-12:
            raise ValueError("Planes are parallel")

        d1 = np.dot(n1, center)
        d2 = np.dot(n2, A)

        # Find one point on the line
        M = np.vstack((n1, n2, v))
        b = np.array([d1, d2, 0.0])
        p0 = np.linalg.solve(M, b)

        # Project A onto the line
        t = np.dot(A - p0, v) / np.dot(v, v)
        return p0 + t * v
    
    def get_subselections(self) -> list[EditorNode]:
        return [self.p0, self.p1, self.p2]
    
    def get_property_list(self) -> dict[str, list[Property]]:
        return {
            "Info":[
                Property("ID", get=lambda _: self.id, type=StringPropertyType()),
                Property("Name", get=lambda _: self.name, set=lambda name, _: setattr(self, 'name', name), type=StringPropertyType()),
                Property("Center X", get=lambda _: self.point[0] if self.point is not None else None, type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Center Y", get=lambda _: self.point[1] if self.point is not None else None, type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Center Z", get=lambda _: self.point[2] if self.point is not None else None, type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Normal X", get=lambda _: self.normal[0] if self.normal is not None else None, type=NumberPropertyType(multiplier=1, decimals=2)),
                Property("Normal Y", get=lambda _: self.normal[1] if self.normal is not None else None, type=NumberPropertyType(multiplier=1, decimals=2)),
                Property("Normal Z", get=lambda _: self.normal[2] if self.normal is not None else None, type=NumberPropertyType(multiplier=1, decimals=2)),
            ],
            "Transform":[
                Property("Mode", get=lambda _: self.mode, set=lambda mode, _: setattr(self, 'mode', mode), type=DropdownPropertyType(options_callback=lambda _: {"Containing":ReferencePlane.Mode.CONTAINING, "Perpendicular":ReferencePlane.Mode.PERPENDICULAR}, tooltips=["Plane contains all 3 points", "Plane is perpendicular to P0 -> P1, and contains P2"])),

                Property("Point 0", get=lambda _: self.p0, set=lambda p, _: setattr(self, 'p0', p), type=DropdownPropertyType(options_callback=lambda scene: {"No Selection": None} | {node.name: node for node in scene.nodes if node != self.p1 and node != self.p2})),
                Property("Point 1", get=lambda _: self.p1, set=lambda p, _: setattr(self, 'p1', p), type=DropdownPropertyType(options_callback=lambda scene: {"No Selection": None} | {node.name: node for node in scene.nodes if node != self.p0 and node != self.p2})),
                Property("Point 2", get=lambda _: self.p2, set=lambda p, _: setattr(self, 'p2', p), type=DropdownPropertyType(options_callback=lambda scene: {"No Selection": None} | {node.name: node for node in scene.nodes if node != self.p0 and node != self.p1})),
            ]
        }
    
    def __str__(self):
        return f"ReferencePlane(name='{self._name}', mode={self._mode}, p0={self._p0}, p1={self._p1}, p2={self._p2})"
    
    def __repr__(self):
        return f"ReferencePlane(name='{self._name}', id={self.id}, mode={self._mode}, p0={self._p0}, p1={self._p1}, p2={self._p2})"
    
    def to_dict(self):
        return {
            'name': self.name,
            'id': str(self.id),
            'mode': self.mode,
            'p0_id': str(self.p0.id),
            'p1_id': str(self.p1.id),
            'p2_id': str(self.p2.id),
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'ReferencePlane':
        mode_str = data['mode']
        if mode_str == "containing":
            mode = ReferencePlane.Mode.CONTAINING
        elif mode_str == "perpendicular":
            mode = ReferencePlane.Mode.PERPENDICULAR
        else:
            raise ValueError(f"Invalid mode: {mode_str}")
        
        plane = ReferencePlane(
            name=data['name'],
            id=UUID(data['id']),
            mode=mode
        )

        plane._p0_id = UUID(data['p0_id']) if data.get('p0_id') is not None else None
        plane._p1_id = UUID(data['p1_id']) if data.get('p1_id') is not None else None
        plane._p2_id = UUID(data['p2_id']) if data.get('p2_id') is not None else None

        return plane


    def fill_references(self, id_to_element: dict[UUID, EditorNode]):
        if not hasattr(self, '_p0_id') or not hasattr(self, '_p1_id') or not hasattr(self, '_p2_id'):
            print("Warning: ReferencePlane does not have '_p0_id', '_p1_id', or '_p2_id' attributes. Cannot fill references.")
            return
        
        self.p0 = id_to_element.get(self._p0_id)
        self.p1 = id_to_element.get(self._p1_id)
        self.p2 = id_to_element.get(self._p2_id)

class NodeGroup(Selectable):

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
                    type=StringPropertyType()
                ),
                Property("Name",
                    get=lambda _: self.name,
                    set=lambda name, _: setattr(self, 'name', name),
                    type=StringPropertyType()
                ),
                Property("Contains",
                    get = lambda _: self.nodes,
                    set = lambda v, _: setattr(self, 'nodes', v),
                    type = GroupPropertyType(all_nodes_callback = lambda scene: scene.nodes)
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