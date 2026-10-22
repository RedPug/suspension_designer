from typing import Any, Callable

import numpy as np

from suspension_designer.editor.commands import LocalModifyElementCommandFactory, NonLocalModifyElementCommandFactory, NonLocalModifyElementCommandFactory
from suspension_designer.elements.nodes import EditorElement
from uuid import UUID

from collections import Counter
from suspension_designer.geometry_core import Geometry, ScalarGeometry, PointGeometry, LineGeometry, PlaneGeometry
from suspension_designer.user_interface.properties import DropdownPropertyEditorFactory, NumberPropertyEditorFactory, StringPropertyEditorFactory, Property


# Base class builds from other reference elements. Each should specify how to build it from other elements
# should also be able to check for self references (can't define a reference based on itself down the chain)
class GeometryElement(EditorElement):
    _all_types: list[type['GeometryElement']] = []

    @classmethod
    def get_valid_reference_sets(cls) -> list[Counter['GeometryElement']]:
        raise NotImplementedError("Subclasses of GeometryElement must implement get_valid_reference_sets method.")

    def __init__(self, name: str, *, id:UUID = None):
        super().__init__(name, id=id)

        self._geometry = None

        self._is_fully_constrained = False

    def is_fully_defined(self) -> bool:
        # print(f"Checking if {self.__class__.__name__} is fully defined with constraint set: {self._constraint_set}, and valid reference sets: {self.__class__.get_valid_reference_sets()}")
        return self._constraint_set in self.__class__.get_valid_reference_sets()

    def get_property_list(self) -> dict[str, list[Property]]:
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
            "Transform":self.get_transform_property_list()
        }

    def get_transform_property_list(self) -> list[Property]:
        return []

    def rebuild_geometry(self):
        if not self.is_fully_defined():
            raise ValueError(f"{self.__class__.__name__} is not fully constrained.")

    def to_dict(self) -> dict:
        raise NotImplementedError("Subclasses of GeometryElement must implement to_dict method.")

    @staticmethod
    def from_dict(data: dict) -> "GeometryElement":
        for cls in GeometryElement._all_types:
            if data.get('type') == cls.type_name:
                if isinstance(cls, ReferenceGeometryElement):
                    return ReferenceGeometryElement.from_dict(data)
                elif isinstance(cls, LiteralGeometryElement):
                    return LiteralGeometryElement.from_dict(data)

        raise ValueError(f"Unknown reference element type: {data['type']}")

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'type_name'):
            # print(f"Registering GeometryElement subclass: {cls.__name__} with type_name: {cls.type_name}")
            GeometryElement._all_types.append(cls)

class ReferenceGeometryElement(GeometryElement):
    def __init__(self, name: str, *, id:UUID = None):
        super().__init__(name, id=id)

        self._constraints: list[GeometryElement] = []
        self._constraint_set: Counter[GeometryElement] = Counter()
        self._update_constraint_set()

    def _get_sorted_geometries(self) -> list[Geometry]:
        geometries = [self._constraints[i]._geometry for i in range(len(self._constraints))]
        geometries.sort(
            key=lambda c: 
            (isinstance(c, ScalarGeometry), 
             isinstance(c, PointGeometry), 
             isinstance(c, LineGeometry), 
             isinstance(c, PlaneGeometry)
            ), 
            reverse=True
        )
        return geometries

    def _update_constraint_set(self):
        self._constraint_set = Counter(constraint._geometry.__class__ for constraint in self._constraints)

    def get_available_constraint_types(self) -> list['GeometryElement']:
        # also account for the case when adding this constraint doesn't make a full set, but only a partial set, so all counters <= the valid sets
        available_constraints: list[type[Geometry]] = []
        for added_constraint in Geometry.ALL_GEOMETRIES:
            new_constraint_set = self._constraint_set + Counter([added_constraint])

            if any(new_constraint_set <= valid_set for valid_set in self.__class__.get_valid_reference_sets()):
                available_constraints.append(added_constraint)
        
        return available_constraints

    def does_reference_element(self, id: UUID) -> bool:
        for constraint in self._constraints:
            if constraint.id == id:
                return True
        return False

    
    def fill_references(self, id_to_element: dict[UUID, EditorElement]):
        # print('filling references...')
        for i, constraint in enumerate(self._constraints):
            if isinstance(constraint, UUID):
                if constraint in id_to_element:
                    element = id_to_element[constraint]
                    if not isinstance(element, GeometryElement):
                        raise ValueError(f"Element with ID {constraint} is not a GeometryElement.")
                    self._constraints[i] = element
                    # print('filled reference for constraint', i, 'with id', constraint, 'to element', id_to_element[constraint].__str__())
                else:
                    raise ValueError(f"Element with ID {constraint} not found in id_to_element mapping.")

        self._update_constraint_set()
        # print('done filling references')
        print()

    def to_dict(self) -> dict:
        constraints = []
        for i, constraint in enumerate(self._constraints):
            if isinstance(constraint, LiteralGeometryElement):
                constraints.append(constraint.to_dict())
            else:
                constraints.append({'id': str(constraint.id)})

        return {
            "name": self.name,
            "id": str(self.id),
            "type": self.__class__.type_name,
            "constraints": constraints
        }

    @staticmethod
    def from_dict(data: dict) -> 'ReferenceGeometryElement':
        # Find the class corresponding to the type
        cls = next((c for c in GeometryElement._all_types if c.type_name == data['type']), None)
        if cls is None:
            raise ValueError(f"Unknown reference element type: {data['type']}")
        
        if not issubclass(cls, ReferenceGeometryElement):
            raise ValueError(f"Class {cls.__name__} is not a subclass of ReferenceGeometryElement.")
        
        element = cls(name=data['name'], id=UUID(data['id']))
        element._constraints = []
        for constraint_data in data.get('constraints', []):
            if 'id' in constraint_data:
                element._constraints.append(UUID(constraint_data['id']))
                # print(f"Deserialized reference to element with ID: {constraint_data['id']}")
            else:
                # If it's a literal geometry, we can create it directly
                literal_element = LiteralGeometryElement.from_dict(constraint_data)
                # print("Deserialized literal geometry element:", literal_element)
                element._constraints.append(literal_element)
        # print(f"Deserialized {element.__class__.__name__} with constraints: {[str(c) for c in element._constraints]}")
        return element

    def __str__(self):
        return f"{self.__class__.__name__}(name={self.name}, id={self.id}, constraints={[c for c in self._constraints]})"

class LiteralGeometryElement(GeometryElement):
    def __init__(self, geometry: Geometry):
        super().__init__(name=geometry.__class__.__name__)
        self._geometry = geometry

    def is_fully_defined(self) -> bool:
        return True

    def rebuild_geometry(self):
        pass

    def get_property_list(self) -> dict[str, list[Property]]:
        return {
            "Transform":self.get_transform_property_list()
        }

    def get_transform_property_list(self) -> list[Property]:
        raise NotImplementedError("Subclasses of LiteralGeometryElement must implement get_transform_property_list.")
    

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "type": self.__class__.type_name
        } | self._geometry.to_dict()

    def __str__(self):
        return f"{self.__class__.__name__}(geometry={self._geometry})"

    @classmethod
    def from_dict(cls, data: dict) -> 'LiteralGeometryElement':
        if cls is not LiteralGeometryElement:
            raise ValueError("from_dict should be called on LiteralGeometryElement class, not subclasses.")
        # Find the class corresponding to the type
        cls = next((c for c in GeometryElement._all_types if c.type_name == data['type']), None)
        if cls is None:
            raise ValueError(f"Unknown literal geometry element type: {data['type']}")
        
        if not issubclass(cls, LiteralGeometryElement):
            raise ValueError(f"Class {cls.__name__} is not a subclass of LiteralGeometryElement.")
        
        element = cls.from_dict(data)
        return element

class ScalarReferenceElement(ReferenceGeometryElement):
    type_name = "scalar"

    @classmethod
    def get_valid_reference_sets(cls) ->list[Counter[Geometry]]:
        return [
            Counter([ScalarGeometry]),
        ]
        
    def __init__(self, name: str, *, id:UUID = None):
        super().__init__(name, id=id)
        self._geometry = ScalarGeometry(0.0)

    def get_transform_property_list(self) -> list[Property]:
        return [
            Property("Value",
                get=lambda _: self._geometry.value,
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=0.1, decimals=3)
            )
        ]

    def rebuild_geometry(self):
        super().rebuild_geometry()
        geometries = self._get_sorted_geometries()
        if self._constraint_set == Counter([ScalarGeometry]):
            self._geometry = ScalarGeometry.from_scalar(geometries[0])

class PointReferenceElement(ReferenceGeometryElement):
    type_name = "point"

    @classmethod
    def get_valid_reference_sets(cls) ->list[Counter[Geometry]]:
        return [
            Counter([PointGeometry]),
            Counter([PointGeometry, PlaneGeometry]),
            Counter([LineGeometry, PlaneGeometry]),
            Counter([PointGeometry, LineGeometry]),
            Counter([LineGeometry, LineGeometry]),
            Counter([PlaneGeometry, PlaneGeometry, PlaneGeometry]),
        ]
        
    def __init__(self, name: str, *, id:UUID = None):
        super().__init__(name, id=id)
        self._geometry = PointGeometry(np.array([0.0, 0.0, 0.0]))

    def get_transform_property_list(self) -> list[Property]:
        return [
            Property("X",
                get=lambda _: self._geometry.pos[0],
                prop_editor=NumberPropertyEditorFactory(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
            ),
            Property("Y",
                get=lambda _: self._geometry.pos[1],
                prop_editor=NumberPropertyEditorFactory(multiplier=1e-3, step=1.0, decimals=2,  suffix=" mm")
            ),
            Property("Z",
                get=lambda _: self._geometry.pos[2],
                prop_editor=NumberPropertyEditorFactory(multiplier=1e-3, step=1.0, decimals=2, suffix=" mm")
            )
        ]

    def __str__(self):
        return f"PointReferenceElement(geometry={self._geometry})"

    def rebuild_geometry(self):
        super().rebuild_geometry()
        # sort constraint set in order of point, line, plane for consistent indexing
        geometries = self._get_sorted_geometries()
        
        if self._constraint_set == Counter([PointGeometry]):
            self._geometry = PointGeometry.from_point(geometries[0])
        elif self._constraint_set == Counter([PointGeometry, PlaneGeometry]):
            self._geometry = PointGeometry.from_point_plane(geometries[0], geometries[1])
        elif self._constraint_set == Counter([LineGeometry, PlaneGeometry]):
            self._geometry = PointGeometry.from_line_plane(geometries[0], geometries[1])
        elif self._constraint_set == Counter([PointGeometry, LineGeometry]):
            self._geometry = PointGeometry.from_point_line(geometries[0], geometries[1])
        elif self._constraint_set == Counter([LineGeometry, LineGeometry]):
            self._geometry = PointGeometry.from_line_line(geometries[0], geometries[1])
        elif self._constraint_set == Counter([PlaneGeometry, PlaneGeometry, PlaneGeometry]):
            self._geometry = PointGeometry.from_plane_plane_plane(geometries[0], geometries[1], geometries[2])

class LineReferenceElement(ReferenceGeometryElement):
    type_name = "line"

    @classmethod
    def get_valid_reference_sets(cls) ->list[Counter[GeometryElement]]:
        return [
            Counter([LineGeometry]),
            Counter([PointGeometry, LineGeometry]),
            Counter([PointGeometry, PointGeometry]),
            Counter([PlaneGeometry, PlaneGeometry]),
            Counter([PointGeometry, PlaneGeometry]),
        ]

    def __init__(self, name: str, *, id:UUID = None):
        super().__init__(name, id=id)
        self._geometry = LineGeometry(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))

    def get_transform_property_list(self) -> list[Property]:
        return [
            Property("Point X",
                get=lambda _: self._geometry.point[0],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0e-3, step=1, decimals=2, suffix=" mm")
            ),
            Property("Point Y",
                get=lambda _: self._geometry.point[1],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0e-3, step=1, decimals=2, suffix=" mm")
            ),
            Property("Point Z",
                get=lambda _: self._geometry.point[2],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0e-3, step=1, decimals=2, suffix=" mm")
            ),
            Property("Direction X",
                get=lambda _: self._geometry.direction[0],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=1, decimals=3)
            ),
            Property("Direction Y",
                get=lambda _: self._geometry.direction[1],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=1, decimals=3)
            ),
            Property("Direction Z",
                get=lambda _: self._geometry.direction[2],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=1, decimals=3)
            )
        ]

    def rebuild_geometry(self):
        super().rebuild_geometry()
        # sort constraint set in order of point, line, plane for consistent indexing
        geometries = self._get_sorted_geometries()
        
        if self._constraint_set == Counter([LineGeometry]):
            self._geometry = LineGeometry.from_line(geometries[0])
        elif self._constraint_set == Counter([PointGeometry, LineGeometry]):
            self._geometry = LineGeometry.from_point_line(geometries[0], geometries[1])
        elif self._constraint_set == Counter([PointGeometry, PointGeometry]):
            self._geometry = LineGeometry.from_point_point(geometries[0], geometries[1])
        elif self._constraint_set == Counter([PlaneGeometry, PlaneGeometry]):
            self._geometry = LineGeometry.from_plane_plane(geometries[0], geometries[1])
        elif self._constraint_set == Counter([PointGeometry, PlaneGeometry]):
            self._geometry = LineGeometry.from_point_plane(geometries[0], geometries[1])

class PlaneReferenceElement(ReferenceGeometryElement):
    type_name = "plane"

    @classmethod
    def get_valid_reference_sets(cls) ->list[Counter[GeometryElement]]:
        return [
            Counter([PlaneGeometry]),
            Counter([PointGeometry, LineGeometry]),
            Counter([PointGeometry, PlaneGeometry]),
            Counter([PointGeometry, PointGeometry, PointGeometry]),
            Counter([ScalarGeometry, PlaneGeometry]),
        ]

    def __init__(self, name: str, *, id:UUID = None):
        super().__init__(name, id=id)
        # print("Initializing PlaneReferenceElement with default geometry.")
        self._geometry = PlaneGeometry(np.array([0, 0, 1]), np.zeros(3))

    def get_transform_property_list(self) -> list[Property]:
        return [
            Property("Point X",
                get=lambda _: self._geometry.point[0],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0e-3, step=1, decimals=2, suffix=" mm")
            ),
            Property("Point Y",
                get=lambda _: self._geometry.point[1],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0e-3, step=1, decimals=2, suffix=" mm")
            ),
            Property("Point Z",
                get=lambda _: self._geometry.point[2],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0e-3, step=1, decimals=2, suffix=" mm")
            ),
            Property("Normal X",
                get=lambda _: self._geometry.normal[0],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=1, decimals=3)
            ),
            Property("Normal Y",
                get=lambda _: self._geometry.normal[1],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=1, decimals=3)
            ),
            Property("Normal Z",
                get=lambda _: self._geometry.normal[2],
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=1, decimals=3)
            )
        ]

    def rebuild_geometry(self):
        super().rebuild_geometry()
        
        geometries = self._get_sorted_geometries()

        if self._constraint_set == Counter([PlaneGeometry]):
            self._geometry = PlaneGeometry.from_plane(geometries[0])
        elif self._constraint_set == Counter([PointGeometry, LineGeometry]):
            self._geometry = PlaneGeometry.from_point_line(geometries[0], geometries[1])
        elif self._constraint_set == Counter([PointGeometry, PlaneGeometry]):
            self._geometry = PlaneGeometry.from_point_plane(geometries[0], geometries[1])
        elif self._constraint_set == Counter([PointGeometry, PointGeometry, PointGeometry]):
            self._geometry = PlaneGeometry.from_point_point_point(geometries[0], geometries[1], geometries[2])
        elif self._constraint_set == Counter([ScalarGeometry, PlaneGeometry]):
            self._geometry = PlaneGeometry.from_scalar_plane(geometries[0], geometries[1])





class LiteralScalarElement(LiteralGeometryElement, ScalarReferenceElement):
    type_name="literal_scalar"

    def __init__(self, value: float, *, id:UUID = None):
        super().__init__(ScalarGeometry(value))
        self._geometry: ScalarGeometry

    @property
    def value(self) -> float:
        return self._geometry.value

    @value.setter
    def value(self, new_value: float):
        self._geometry.value = new_value
        self.did_change.emit()

    def get_transform_property_list(self) -> list[Property]:
        return [
            Property("Value",
                get=lambda _: self.value,
                set=NonLocalModifyElementCommandFactory(element_id=self.id, property_name='value'),
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=0.1, decimals=3)
            )
        ]

class LiteralPointElement(LiteralGeometryElement, PointReferenceElement):
    type_name="literal_point"
    

    def __init__(self, point: np.ndarray, *, id:UUID = None):
        super().__init__(PointGeometry(point))
        self._geometry: PointGeometry

    @property
    def x(self) -> float:
        return self._geometry.pos[0]

    @x.setter
    def x(self, new_x: float):
        self._geometry.pos[0] = new_x

    @property
    def y(self) -> float:
        return self._geometry.pos[1]

    @y.setter
    def y(self, new_y: float):
        self._geometry.pos[1] = new_y

    @property
    def z(self) -> float:
        return self._geometry.pos[2]

    @z.setter
    def z(self, new_z: float):
        self._geometry.pos[2] = new_z

    def get_transform_property_list(self) -> list[Property]:
        return [
            Property("X",
                get=lambda _: self.x,
                set=NonLocalModifyElementCommandFactory(element_id=self.id, property_name='x'),
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=0.1, decimals=3)
            ),
            Property("Y",
                get=lambda _: self.y,
                set=NonLocalModifyElementCommandFactory(element_id=self.id, property_name='y'),
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=0.1, decimals=3)
            ),
            Property("Z",
                get=lambda _: self.z,
                set=NonLocalModifyElementCommandFactory(element_id=self.id, property_name='z'),
                prop_editor=NumberPropertyEditorFactory(multiplier=1.0, step=0.1, decimals=3)
            )
        ]

    def to_dict(self) -> dict:
        return {
            "type": self.__class__.type_name,
            "point": self._geometry.pos.tolist()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LiteralPointElement':
        if cls is not LiteralPointElement:
            raise ValueError("from_dict should be called on LiteralPointElement class, not subclasses.")
        
        return cls(point=np.array(data['point']))