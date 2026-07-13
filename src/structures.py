from enum import Enum, StrEnum, auto
from time import perf_counter
from typing import Any, Callable, List, Literal, Optional, Union
from uuid import UUID, uuid4

from PySide6.QtCore import (QObject, Signal)

import numpy as np

# from src.solver import SolverState, solve_system, SolverResult
from src.properties import DropdownPropertyType, GroupPropertyType, NumberPropertyType, Property, StringPropertyType
# from src.scene import SceneState



class EditorNode(QObject):
    did_change = Signal()  # Signal to emit when the node's properties change

    def __init__(self, name: str, world_position: np.ndarray, id: UUID = None):
        super().__init__()
        
        self._id = uuid4() if id is None else id
        self._name = name
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

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        self.did_change.emit()

    @property
    def id(self):
        return self._id
    
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

class ReferencePlane(QObject):
    did_change = Signal()  # Signal to emit when the plane's properties change

    class Mode(StrEnum):
        CONTAINING = auto()
        PERPENDICULAR = auto()

    def __init__(self, p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, mode: 'ReferencePlane.Mode', name: str = "Unnamed", id: UUID = None):
        super().__init__()
        
        
        self._name = name
        self.id = id if id is not None else uuid4()

        self._mode = mode
        self._p0 = p0
        self._p1 = p1
        self._p2 = p2

        self._rebuild()

    def _rebuild(self):
        if self.mode == ReferencePlane.Mode.CONTAINING:
            # Recreate a plane containing the three points
            v1 = self._p1 - self._p0
            v2 = self._p2 - self._p0
            normal = np.cross(v1, v2)
            normal /= np.linalg.norm(normal)
            point = self._p0
        elif self.mode == ReferencePlane.Mode.PERPENDICULAR:
            # Recreate a plane perpendicular to the vector from p0 to p1, passing through p2
            v = self._p1 - self._p0
            normal = v / np.linalg.norm(v)
            point = self._p2
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
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        self.did_change.emit()

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
    
    def get_property_list(self) -> dict[str, list[Property]]:
        return {
            "Info":[
                Property("ID", get=lambda _: self.id, type=StringPropertyType()),
                Property("Name", get=lambda _: self.name, set=lambda name, _: setattr(self, 'name', name), type=StringPropertyType()),
                Property("Center X", get=lambda _: self.point[0], type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Center Y", get=lambda _: self.point[1], type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Center Z", get=lambda _: self.point[2], type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Normal X", get=lambda _: self.normal[0], type=NumberPropertyType(multiplier=1, decimals=2)),
                Property("Normal Y", get=lambda _: self.normal[1], type=NumberPropertyType(multiplier=1, decimals=2)),
                Property("Normal Z", get=lambda _: self.normal[2], type=NumberPropertyType(multiplier=1, decimals=2)),
            ],
            "Transform":[
                Property("Mode", get=lambda _: self.mode, set=lambda mode, _: setattr(self, 'mode', mode), type=DropdownPropertyType(options_callback=lambda _: {"Containing":ReferencePlane.Mode.CONTAINING, "Perpendicular":ReferencePlane.Mode.PERPENDICULAR}, tooltips=["Plane contains all 3 points", "Plane is perpendicular to P0 -> P1, and contains P2"])),

                Property("X0", get=lambda _: self.p0[0], set=lambda x, _: setattr(self, 'p0', np.array([x, self.p0[1], self.p0[2]])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Y0", get=lambda _: self.p0[1], set=lambda y, _: setattr(self, 'p0', np.array([self.p0[0], y, self.p0[2]])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Z0", get=lambda _: self.p0[2], set=lambda z, _: setattr(self, 'p0', np.array([self.p0[0], self.p0[1], z])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),

                Property("X1", get=lambda _: self.p1[0], set=lambda x, _: setattr(self, 'p1', np.array([x, self.p1[1], self.p1[2]])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Y1", get=lambda _: self.p1[1], set=lambda y, _: setattr(self, 'p1', np.array([self.p1[0], y, self.p1[2]])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Z1", get=lambda _: self.p1[2], set=lambda z, _: setattr(self, 'p1', np.array([self.p1[0], self.p1[1], z])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),

                Property("X2", get=lambda _: self.p2[0], set=lambda x, _: setattr(self, 'p2', np.array([x, self.p2[1], self.p2[2]])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Y2", get=lambda _: self.p2[1], set=lambda y, _: setattr(self, 'p2', np.array([self.p2[0], y, self.p2[2]])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
                Property("Z2", get=lambda _: self.p2[2], set=lambda z, _: setattr(self, 'p2', np.array([self.p2[0], self.p2[1], z])), type=NumberPropertyType(multiplier=1e-3, decimals=2, suffix=" mm")),
            ]
        }
    
    def __str__(self):
        return f"ReferencePlane(name='{self._name}', mode={self._mode}, p0={self._p0.tolist()}, p1={self._p1.tolist()}, p2={self._p2.tolist()})"
    
    def __repr__(self):
        return f"ReferencePlane(name='{self._name}', id={self.id}, mode={self._mode}, p0={self._p0.tolist()}, p1={self._p1.tolist()}, p2={self._p2.tolist()})"
    
    def to_dict(self):
        return {
            'name': self.name,
            'id': str(self.id),
            'mode': self.mode,
            'p0': self.p0.tolist(),
            'p1': self.p1.tolist(),
            'p2': self.p2.tolist(),
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
        
        return ReferencePlane(
            name=data['name'],
            id=UUID(data['id']),
            p0=np.array(data['p0'], dtype=float),
            p1=np.array(data['p1'], dtype=float),
            p2=np.array(data['p2'], dtype=float),
            mode=mode
        )

class NodeGroup(QObject):
    did_change = Signal()

    def __init__(self, name: str, *, id:UUID = None, nodes: list[EditorNode]):
        super().__init__()
        self._name = name
        self.id = id if id is not None else uuid4()
        self._nodes = nodes

    @property
    def name(self):
        return self._name
    
    @name.setter
    def name(self, value):
        self._name = value
        self.did_change.emit()

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

Selectable = Union[EditorNode, ReferencePlane]

class SelectionManager(QObject):
    selection_changed = Signal()  # Signal to emit when selection changes

    def __init__(self):
        super().__init__()

        self._selected_object: Selectable = None
        self._subselections: list[Selectable] = []

        self.selection_changed.connect(lambda: print(f"Selection changed to: {self._selected_object}"))

    def on_selection_modified(self):
        self._update_subselections()
        self.selection_changed.emit()

    def _update_subselections(self):
        if self._selected_object is None:
            self._subselections = []
        else:
            if hasattr(self._selected_object, 'get_subselections'):
                self._subselections = self._selected_object.get_subselections()
            else:
                self._subselections = []

    def set_selected(self, item: Selectable):
        if self._selected_object == item:
            return  # No change in selection
        
        if self._selected_object is not None:
            self._selected_object.did_change.disconnect(self.on_selection_modified)

        self._selected_object = item

        if self._selected_object is not None:
            self._selected_object.did_change.connect(self.on_selection_modified)

        # self._update_subselections()

        self.on_selection_modified()

    def get_selected(self) -> Selectable:
        return self._selected_object

    @property
    def subselections(self) -> list[Selectable]:
        return self._subselections