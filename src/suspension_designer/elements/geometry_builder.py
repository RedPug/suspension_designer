from collections import deque

from time import perf_counter

from suspension_designer.elements.geometry import GeometryElement, LiteralGeometryElement, ReferenceGeometryElement




class GeometryBuilder:
    def __init__(self, elements: list[GeometryElement]):
        self.elements = elements
        self._order_cache = None

    def rebuild_all_geometry(self):
        t0 = perf_counter()

        n = len(self.elements)


        # This is the worst possible case where only one element per cycle can be built before looping back.
        # n + n-1 + ... + 1 = n*(n+1)/2
        max_iterations = n * (n+1) / 2

        # If we have a cached order from a previous rebuild, we can use it to try to build the elements in that order first.
        # Advantage: if the order is correct, we can build all elements in one pass.
        # Disadvantage: doesn't order new elements correctly, and has a small cost.
        if self._order_cache is not None:
            # sort the elements according to the cached order
            sorted_elements = sorted(self.elements, key=lambda e: self._order_cache.index(e) if e in self._order_cache else float('inf'))
            remaining_elements = deque(sorted_elements)
        else:
            remaining_elements = deque(self.elements)

        built_elements = []
        iterations = 0
        while remaining_elements:
            iterations += 1
            if iterations > max_iterations:
                break

            next_element = remaining_elements.popleft()
            if isinstance(next_element, LiteralGeometryElement):
                print("Warning: LiteralGeometryElement should not be in the rebuild queue. It should be rebuilt as a dependency of a ReferenceGeometryElement.")
                pass
            elif isinstance(next_element, ReferenceGeometryElement):
                if not next_element.is_fully_defined():
                    continue
                if all(
                    constraint in built_elements
                    or isinstance(constraint, LiteralGeometryElement)
                    or (
                        not isinstance(constraint, ReferenceGeometryElement)
                        and hasattr(constraint, "_geometry")
                        and constraint._geometry is not None
                    )
                    for constraint in next_element._constraints
                ):
                    # literal constraints are always considered "built" since they don't need to be rebuilt
                    next_element.rebuild_geometry()
                    built_elements.append(next_element)
                else:
                    # put it back at the end of the queue to try again later
                    remaining_elements.append(next_element)
            else:
                raise ValueError(f"Unknown GeometryElement type: {type(next_element)}")

        self._order_cache = built_elements

        t1 = perf_counter()
        if t1-t0 > 0.01:
            print("Warning: geometry rebuild took longer than expected:", (t1-t0)*1000, "ms")

        print(f"Geometry rebuild completed in {iterations}/{max_iterations} iterations, {len(built_elements)} elements built, time taken: {(t1-t0)*1000:.2f} ms")