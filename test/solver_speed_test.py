import numpy as np
import matplotlib.pyplot as plt

from suspension_designer.document import Document, MotionDocument
from suspension_designer.solver import solve_at_time
from suspension_designer.solver_deprecated import solve as old_solve

doc: MotionDocument = Document.load("./user_data/my_motion.proj")

fig, ax = plt.subplots()


result_new = solve_at_time(
    doc.motion_data.variables,
    time_value=0.0,
    scene_state=doc.scene_state)

ax.plot(result_new.errors, label="New")

result_old = old_solve(doc.scene_state, doc.motion_data.variables, t=0.0)

ax.plot(result_old.errors, label="old")
    
ax.set_yscale('log')
ax.set_xscale('log')
ax.set_ylabel('Error (log scale)')
ax.set_xlabel('Iteration')
ax.set_title('Error Convergence of Fixed Displacement Solver')
ax.legend()
ax.grid()

plt.show()