from collections import deque

from time import perf_counter

from suspension_designer.elements.geometry import GeometryElement, LiteralGeometryElement, ReferenceGeometryElement




class GeometryBuilder:
    def __init__(self, elements: list[GeometryElement]):
        self.elements = elements

    def rebuild_all_geometry(self):
        t0 = perf_counter()

        remaining_elements = deque(self.elements)
        built_elements = []
        while remaining_elements:
            next_element = remaining_elements.popleft()
            if isinstance(next_element, LiteralGeometryElement):
                next_element.rebuild_geometry()
                built_elements.append(next_element)
            elif isinstance(next_element, ReferenceGeometryElement):
                if all(constraint in built_elements for constraint in next_element._constraints):
                    next_element.rebuild_geometry()
                    built_elements.append(next_element)
                else:
                    for constraint in next_element._constraints:
                        if constraint not in built_elements and constraint not in remaining_elements:
                            remaining_elements.append(constraint)
                    remaining_elements.append(next_element)
            else:
                raise ValueError(f"Unknown GeometryElement type: {type(next_element)}")

        t1 = perf_counter()
        if t1-t0 > 0.01:
            print("Warning: geometry rebuild took longer than expected:", (t1-t0)*1000, "ms")