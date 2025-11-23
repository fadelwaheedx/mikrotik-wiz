
function filterScripts() {
    const input = document.getElementById('searchInput');
    const filter = input.value.toUpperCase();
    const ul = document.getElementById('navList');
    const li = ul.getElementsByTagName('li');

    for (let i = 0; i < li.length; i++) {
        const a = li[i].getElementsByTagName("a")[0];
        const txtValue = a.textContent || a.innerText;
        if (txtValue.toUpperCase().indexOf(filter) > -1) {
            li[i].classList.remove('hidden');
        } else {
            li[i].classList.add('hidden');
        }
    }
}
