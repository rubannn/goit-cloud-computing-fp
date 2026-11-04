const $ = (id) => document.getElementById(id);
let editingId = null;
let offset = 0;
let listRequest = 0;
const pageSize = 20;

function message(text, error = false) {
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    if (response.status === 422) throw new Error("Проверьте поля: цитата не должна быть пустой или слишком длинной.");
    if (response.status === 404) throw new Error("Цитата не найдена. Обновите список или измените фильтры.");
    throw new Error("Не удалось выполнить запрос. Попробуйте ещё раз.");
  }
  return response.status === 204 ? null : response.json();
}

function filters() {
  return new URLSearchParams({ q: $("search").value.trim(), category: $("filter-category").value });
}

function resetForm() {
  editingId = null;
  $("quote-form").reset();
  $("form-title").textContent = "Добавить цитату";
  $("cancel").hidden = true;
}

function renderQuote(quote) {
  const card = document.createElement("article");
  card.className = "quote";
  const body = document.createElement("blockquote");
  body.textContent = quote.text;
  const author = document.createElement("p");
  author.className = "byline";
  author.textContent = quote.author || "Неизвестный автор";
  card.append(body, author);
  if (quote.category) {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = quote.category;
    card.append(tag);
  }
  const actions = document.createElement("div");
  actions.className = "actions";
  const edit = document.createElement("button");
  edit.className = "secondary";
  edit.textContent = "Изменить";
  edit.onclick = () => {
    editingId = quote.id;
    for (const key of ["text", "author", "category"]) $(key).value = quote[key];
    $("form-title").textContent = "Изменить цитату";
    $("cancel").hidden = false;
    $("text").focus();
  };
  const remove = document.createElement("button");
  remove.className = "secondary danger";
  remove.textContent = "Удалить";
  remove.onclick = async () => {
    if (!confirm("Удалить эту цитату?")) return;
    remove.disabled = true;
    try {
      await api(`/api/quotes/${quote.id}`, { method: "DELETE" });
      if (editingId === quote.id) resetForm();
      await refresh();
      message("Цитата удалена.");
    } catch (error) { message(error.message, true); }
    finally { remove.disabled = false; }
  };
  actions.append(edit, remove);
  card.append(actions);
  return card;
}

async function loadQuotes(append = false) {
  const request = ++listRequest;
  const params = filters();
  params.set("offset", append ? offset : 0);
  params.set("limit", pageSize);
  const quotes = await api(`/api/quotes?${params}`);
  if (request !== listRequest) return;
  if (!append) { $("quotes").replaceChildren(); offset = 0; }
  quotes.forEach((quote) => $("quotes").append(renderQuote(quote)));
  offset += quotes.length;
  $("more").hidden = quotes.length < pageSize;
  message(offset ? `Показано цитат: ${offset}` : "Пока ничего нет. Добавьте цитату или измените фильтры.");
}

async function loadCategories() {
  const selected = $("filter-category").value;
  const categories = await api("/api/categories");
  $("category-options").replaceChildren();
  $("filter-category").replaceChildren(new Option("Все категории", ""));
  categories.forEach((category) => {
    $("category-options").append(new Option(category, category));
    $("filter-category").append(new Option(category, category));
  });
  // Preserve a deleted category's filter so deletion does not unexpectedly show all quotes.
  if (selected && !categories.includes(selected)) $("filter-category").append(new Option(selected, selected));
  $("filter-category").value = selected;
}

async function refresh() { await loadCategories(); await loadQuotes(); }

$("quote-form").onsubmit = async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(["text", "author", "category"].map((key) => [key, $(key).value.trim()]));
  if (!payload.text) { message("Введите текст цитаты.", true); return; }
  $("save").disabled = true;
  try {
    await api(editingId === null ? "/api/quotes" : `/api/quotes/${editingId}`, {
      method: editingId === null ? "POST" : "PUT", body: JSON.stringify(payload),
    });
    resetForm();
    await refresh();
    message("Цитата сохранена. Если её не видно, проверьте фильтры.");
  } catch (error) { message(error.message, true); }
  finally { $("save").disabled = false; }
};
$("cancel").onclick = resetForm;
$("filters").onsubmit = (event) => { event.preventDefault(); loadQuotes().catch((error) => message(error.message, true)); };
$("filter-category").onchange = () => loadQuotes().catch((error) => message(error.message, true));
$("more").onclick = async () => {
  $("more").disabled = true;
  try { await loadQuotes(true); } catch (error) { message(error.message, true); }
  finally { $("more").disabled = false; }
};
$("random").onclick = async () => {
  const request = ++listRequest;
  try {
    const quote = await api(`/api/quotes/random?${filters()}`);
    if (request !== listRequest) return;
    $("quotes").replaceChildren(renderQuote(quote));
    $("more").hidden = true;
    message("Случайная цитата из выбранной подборки. Нажмите «Найти», чтобы вернуться к списку.");
  } catch (error) { if (request === listRequest) message(error.message, true); }
};
refresh().catch((error) => message(error.message, true));
