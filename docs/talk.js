"use strict";

const film = document.getElementById("film");
const chapters = [
  [0, "0:00", "The benchmark"],
  [150, "2:30", "The decoder"],
  [300, "5:00", "The experiment"],
  [450, "7:30", "The workbench"],
];
const buttons = chapters.map(([seconds, timestamp, title]) => {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = timestamp + " · " + title;
  button.addEventListener("click", () => {
    film.currentTime = seconds;
    film.play().catch(() => film.focus());
  });
  document.getElementById("chapters").append(button);
  return button;
});
function highlightChapter() {
  const index = Math.min(3, Math.floor(film.currentTime / 150));
  buttons.forEach((button, i) =>
    button.setAttribute("aria-current", String(i === index)),
  );
}
film.addEventListener("timeupdate", highlightChapter);
highlightChapter();
