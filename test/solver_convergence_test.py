import numpy as np
import matplotlib.pyplot as plt

from suspension_designer.document import Document, MotionDocument
from suspension_designer.solver import solve

doc: MotionDocument = Document.load("./user_data/my_motion.proj")
print(doc)


fig, ax = plt.subplots()

for easing in np.arange(0.1, 1.7 + 0.1, 0.1):
    result = solve(doc.scene_state, doc.motion_data.variables, t=0.0, easing_factor=easing, max_iterations=1e4, epsilon=1e-9)
    ax.plot(np.arange(len(result.errors)), result.errors, '-', label=f"Easing: {easing:.2f}")

ax.set_yscale('log')
ax.set_xscale('log')
ax.set_ylabel('Error (log scale)')
ax.set_xlabel('Iteration')
ax.set_title('Error Convergence of Fixed Displacement Solver')
ax.legend()
ax.grid()

plt.show()