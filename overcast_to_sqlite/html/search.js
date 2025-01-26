function searchEps(searchString) {
  const divs = Array.from(document.getElementsByTagName('section'));
  divs.forEach(div => {
    const matches = div.innerText.toLowerCase().includes(searchString.toLowerCase());
    if (matches) {
        div.style.display = 'flex';
    } else {
        div.style.display = 'none';
    }
  });
}