import numpy as np

ALL_GEOMETRIES: list[type['Geometry']] = []

# representation of a certain number of DOF restrictions.
class Geometry():
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        ALL_GEOMETRIES.append(cls)

    def to_dict(self) -> dict:
        return {
            "type": self.__class__.__name__
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Geometry':
        if cls is not Geometry:
            raise NotImplementedError("from_dict should be called on the base Geometry class, not a subclass.")
        
        geometry_type = data.get("type")
        for geometry_cls in ALL_GEOMETRIES:
            if geometry_cls.__name__ == geometry_type:
                return geometry_cls.from_dict(data)
            
        raise ValueError(f"Unknown geometry type: {geometry_type}")

# represents a scalar for various purposes.
class ScalarGeometry(Geometry):
    def __init__(self, value):
        super().__init__()
        self.value = float(value)

    def from_scalar(scalar: 'ScalarGeometry') -> 'ScalarGeometry':
        assert isinstance(scalar, ScalarGeometry), "Input must be a ScalarGeometry"
        return ScalarGeometry(scalar.value)

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "value": self.value
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ScalarGeometry':
        if cls is not ScalarGeometry:
            raise NotImplementedError("from_dict should be called on the base ScalarGeometry class, not a subclass.")
        
        return ScalarGeometry(data['value'])

# constraining to a point
class PointGeometry(Geometry):
    def __init__(self, pos):
        super().__init__()
        self.pos = np.array(pos)

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "point": self.pos.tolist()
        }

    def __str__(self):
        return f"PointGeometry(pos={self.pos})"

    @classmethod
    def from_dict(cls, data: dict) -> 'PointGeometry':
        if cls is not PointGeometry:
            raise NotImplementedError("from_dict should be called on the base PointGeometry class, not a subclass.")
        
        return PointGeometry(data['point'])

    @staticmethod
    def from_point(point: 'PointGeometry') -> 'PointGeometry':
        return PointGeometry(point.pos)
    
    @staticmethod
    def from_point_plane(point: 'PointGeometry', plane: 'PlaneGeometry') -> 'PointGeometry':
        assert isinstance(point, PointGeometry), "First input must be a PointGeometry"
        assert isinstance(plane, PlaneGeometry), "Second input must be a PlaneGeometry"

        delta = point.pos - plane.point
        projected_point = point.pos - np.dot(delta, plane.normal) * plane.normal
        return PointGeometry(projected_point)


    @staticmethod
    def from_point_line(point: 'PointGeometry', line: 'LineGeometry') -> 'PointGeometry':
        assert isinstance(point, PointGeometry), "First input must be a PointGeometry"
        assert isinstance(line, LineGeometry), "Second input must be a LineGeometry"

        delta = point.pos - line.point
        projected_point = line.point + np.dot(delta, line.direction) * line.direction
        return PointGeometry(projected_point)

    @staticmethod
    def from_line_line(line1: 'LineGeometry', line2: 'LineGeometry') -> 'PointGeometry':
        assert isinstance(line1, LineGeometry), "First input must be a LineGeometry"
        assert isinstance(line2, LineGeometry), "Second input must be a LineGeometry"

        # closest point between two lines. First, find where the two lines meet closest to each other,
        # then take the midpoint of the segment connecting the closest points.
        p1 = line1.point
        d1 = line1.direction
        p2 = line2.point
        d2 = line2.direction

        cross_d1_d2 = np.cross(d1, d2)
        denom = np.linalg.norm(cross_d1_d2) ** 2
        if denom == 0:
            # Lines are parallel, return midpoint between points on the lines
            projected_point = (p1 + p2) / 2
        else:
            t = np.dot(np.cross((p2 - p1), d2), cross_d1_d2) / denom
            closest_point_line1 = p1 + t * d1
            closest_point_line2 = p2 + np.dot((closest_point_line1 - p2), d2) * d2
            projected_point = (closest_point_line1 + closest_point_line2) / 2

        return PointGeometry(projected_point)

    @staticmethod
    def from_line_plane(line: 'LineGeometry', plane: 'PlaneGeometry') -> 'PointGeometry':
        assert isinstance(line, LineGeometry), "First input must be a LineGeometry"
        assert isinstance(plane, PlaneGeometry), "Second input must be a PlaneGeometry"


        #intersection between line and plane
        p0 = line.point
        d = line.direction
        n = plane.normal
        p_plane = plane.point

        denom = np.dot(n, d)
        if denom == 0:
            # Line is parallel to the plane, return a point on the line closest to the plane
            projected_point = p0 - np.dot((p0 - p_plane), n) * n
        else:
            t = np.dot(n, (p_plane - p0)) / denom
            projected_point = p0 + t * d

        return PointGeometry(projected_point)

    @staticmethod
    def from_plane_plane_plane(plane1: 'PlaneGeometry', plane2: 'PlaneGeometry', plane3: 'PlaneGeometry') -> 'PointGeometry':
        assert isinstance(plane1, PlaneGeometry), "First input must be a PlaneGeometry"
        assert isinstance(plane2, PlaneGeometry), "Second input must be a PlaneGeometry"
        assert isinstance(plane3, PlaneGeometry), "Third input must be a PlaneGeometry"
        # intersection between 3 planes

        n1 = plane1.normal
        n2 = plane2.normal
        n3 = plane3.normal
        p1 = plane1.point
        p2 = plane2.point
        p3 = plane3.point

        # Solve the system of linear equations to find the intersection point
        A = np.array([n1, n2, n3])
        b = np.array([np.dot(n1, p1), np.dot(n2, p2), np.dot(n3, p3)])
        projected_point = np.linalg.solve(A, b)

        return PointGeometry(projected_point)



# constraining to a line
class LineGeometry(Geometry):
    def __init__(self, point, direction):
        assert np.linalg.norm(np.array(direction)) > 0, "Direction vector cannot be zero"
        super().__init__()
        self.point = np.array(point)
        self.direction = np.array(direction)
        self.direction = self.direction / np.linalg.norm(self.direction)  # Ensure direction is normalized

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "point": self.point.tolist(),
            "direction": self.direction.tolist()
        }

    def __str__(self):
        return f"LineGeometry(point={self.point}, direction={self.direction})"

    @classmethod
    def from_dict(cls, data: dict) -> 'LineGeometry':
        if cls is not LineGeometry:
            raise NotImplementedError("from_dict should be called on the base LineGeometry class, not a subclass.")
        
        return LineGeometry(data['point'], data['direction'])

    @staticmethod
    def from_line(line: 'LineGeometry') -> 'LineGeometry':
            assert isinstance(line, LineGeometry), "Input must be a LineGeometry"
            # Implement the logic to create a line from a single line constraint
            return line

    @staticmethod
    def from_point_line(point: 'PointGeometry', line: 'LineGeometry') -> 'LineGeometry':
        assert isinstance(point, PointGeometry), "First input must be a PointGeometry"
        assert isinstance(line, LineGeometry), "Second input must be a LineGeometry"
        # parallel to exisitng line, passing through the given point
        direction = line.direction
        origin = point.pos
        return LineGeometry(origin, direction)

    @staticmethod
    def from_point_point(point1: 'PointGeometry', point2: 'PointGeometry') -> 'LineGeometry':
        assert isinstance(point1, PointGeometry), "First input must be a PointGeometry"
        assert isinstance(point2, PointGeometry), "Second input must be a PointGeometry"
        # create a line passing through the two given points
        origin = point1.pos
        direction = point2.pos - point1.pos
        return LineGeometry(origin, direction)

    @staticmethod
    def from_plane_plane(plane1: 'PlaneGeometry', plane2: 'PlaneGeometry') -> 'LineGeometry':
        assert isinstance(plane1, PlaneGeometry), "First input must be a PlaneGeometry"
        assert isinstance(plane2, PlaneGeometry), "Second input must be a PlaneGeometry"
        # intersection line of two planes
        direction = np.cross(plane1.normal, plane2.normal)
        # To find a point on the line, solve the system of plane equations
        A = np.array([plane1.normal, plane2.normal])
        b = np.array([np.dot(plane1.normal, plane1.point), np.dot(plane2.normal, plane2.point)])
        # Use least squares to find a point on the line
        origin = np.linalg.lstsq(A, b, rcond=None)[0]
        return LineGeometry(origin, direction)

    @staticmethod
    def from_point_plane(point: 'PointGeometry', plane: 'PlaneGeometry') -> 'LineGeometry':
        assert isinstance(point, PointGeometry), "First input must be a PointGeometry"
        assert isinstance(plane, PlaneGeometry), "Second input must be a PlaneGeometry"
        # line passing through the point and perpendicular to the plane
        direction = plane.normal
        origin = point.pos
        return LineGeometry(origin, direction)



# constraining to a plane
class PlaneGeometry(Geometry):
    def __init__(self, normal, point):
        assert np.linalg.norm(np.array(normal)) > 0, "Normal vector cannot be zero"
        super().__init__()
        self.normal = np.array(normal) / np.linalg.norm(np.array(normal))
        self.point = np.array(point)

    def to_dict(self) -> dict:
        return super().to_dict() | {
            "normal": self.normal.tolist(),
            "point": self.point.tolist()
        }

    def __str__(self):
        return f"PlaneGeometry(normal={self.normal}, point={self.point})"

    @classmethod
    def from_dict(cls, data: dict) -> 'PlaneGeometry':
        if cls is not PlaneGeometry:
            raise NotImplementedError("from_dict should be called on the base PlaneGeometry class, not a subclass.")
        
        return PlaneGeometry(data['normal'], data['point'])

    @staticmethod
    def from_plane(plane: 'PlaneGeometry') -> 'PlaneGeometry':
        assert isinstance(plane, PlaneGeometry), "Input must be a PlaneGeometry"
        # plane passing through the point and parallel to the given plane
        return PlaneGeometry(plane.normal, plane.point)
    
    @staticmethod
    def from_point_line(point: 'PointGeometry', line: 'LineGeometry') -> 'PlaneGeometry':
        assert isinstance(point, PointGeometry), "First input must be a PointGeometry"
        assert isinstance(line, LineGeometry), "Second input must be a LineGeometry"

        return PlaneGeometry(line.direction, point.pos)

    @staticmethod
    def from_point_plane(point: 'PointGeometry', plane: 'PlaneGeometry') -> 'PlaneGeometry':
        assert isinstance(point, PointGeometry), "First input must be a PointGeometry"
        assert isinstance(plane, PlaneGeometry), "Second input must be a PlaneGeometry"
        # plane passing through the point and parallel to the given plane
        normal = plane.normal
        point_on_plane = point.pos
        return PlaneGeometry(normal, point_on_plane)

    @staticmethod
    def from_point_point_point(point1: 'PointGeometry', point2: 'PointGeometry', point3: 'PointGeometry') -> 'PlaneGeometry':
        assert isinstance(point1, PointGeometry), "First input must be a PointGeometry"
        assert isinstance(point2, PointGeometry), "Second input must be a PointGeometry"
        assert isinstance(point3, PointGeometry), "Third input must be a PointGeometry"
        print("Creating plane from three points:", point1.pos, point2.pos, point3.pos)
        # plane passing through the three given points
        v1 = point2.pos - point1.pos
        v2 = point3.pos - point1.pos
        normal = np.cross(v1, v2)
        point_on_plane = (point1.pos + point2.pos + point3.pos) / 3
        print("Computed normal:", normal, "Point on plane:", point_on_plane)
        return PlaneGeometry(normal, point_on_plane)

    @staticmethod
    def from_scalar_plane(scalar: 'ScalarGeometry', plane: 'PlaneGeometry') -> 'PlaneGeometry':
        assert isinstance(scalar, ScalarGeometry), "First input must be a ScalarGeometry"
        assert isinstance(plane, PlaneGeometry), "Second input must be a PlaneGeometry"
        # plane passing through the point and parallel to the given plane
        normal = plane.normal
        point_on_plane = plane.point + scalar.value * plane.normal
        return PlaneGeometry(normal, point_on_plane)