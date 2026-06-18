const projectButtons = document.querySelectorAll("[data-project]");
const projectViews = document.querySelectorAll(".project-view");

function switchProject(projectId) {
  projectButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.project === projectId);
  });

  projectViews.forEach((view) => {
    const isActive = view.id === `project-${projectId}`;
    view.classList.toggle("active", isActive);
    view.hidden = !isActive;
  });

  if (projectId === "2" && typeof window.initProject2 === "function") {
    window.initProject2();
  }
}

projectButtons.forEach((btn) => {
  btn.addEventListener("click", () => switchProject(btn.dataset.project));
});

switchProject("1");
