const inventory = await fetch("../data/inventory.json").then((response) => response.json());

const searchInput = document.getElementById("search");
const clearSearchButton = document.getElementById("clear-search");
const filtersEl = document.getElementById("filters");
const productListEl = document.getElementById("product-list");
const resultCountEl = document.getElementById("result-count");
const statsEl = document.getElementById("stats");
const emptyStateEl = document.getElementById("empty-state");
const sheetBackdrop = document.getElementById("sheet-backdrop");
const closeDetailButton = document.getElementById("close-detail");
const detailCategoryEl = document.getElementById("detail-category");
const detailTitleEl = document.getElementById("detail-title");
const detailBodyEl = document.getElementById("detail-body");

let activeCategory = "All";
let query = "";

const categories = [
  "All",
  ...new Set(inventory.map((item) => item.category).sort((a, b) => a.localeCompare(b))),
];

function formatQuantity(item) {
  if (item.quantity === null || item.quantity === undefined) {
    return "—";
  }
  const value = Number.isInteger(item.quantity) ? item.quantity : item.quantity;
  return `${value} ${item.unit || ""}`.trim();
}

function formatPrice(price) {
  if (price === null || price === undefined) {
    return "Not listed";
  }
  return `$${price.toFixed(2)}`;
}

function stockStatus(item) {
  const quantity = item.quantity ?? 0;
  if (quantity <= 0) {
    return { label: "Out of stock", className: "out" };
  }
  if (item.minLevel !== null && quantity <= item.minLevel) {
    return { label: "Low stock", className: "low" };
  }
  return { label: "In stock", className: "ok" };
}

function matchesQuery(item, text) {
  if (!text) {
    return true;
  }
  const haystack = [item.name, item.category, item.id, item.notes].join(" ").toLowerCase();
  return haystack.includes(text);
}

function getFilteredItems() {
  const text = query.trim().toLowerCase();
  return inventory.filter((item) => {
    const categoryMatch = activeCategory === "All" || item.category === activeCategory;
    return categoryMatch && matchesQuery(item, text);
  });
}

function renderStats() {
  const outOfStock = inventory.filter((item) => (item.quantity ?? 0) <= 0).length;
  const priced = inventory.filter((item) => item.price !== null).length;

  statsEl.innerHTML = `
    <div class="stat-chip"><strong>${inventory.length}</strong> products</div>
    <div class="stat-chip"><strong>${outOfStock}</strong> out of stock</div>
    <div class="stat-chip"><strong>${priced}</strong> with price</div>
  `;
}

function renderFilters() {
  filtersEl.innerHTML = categories
    .map(
      (category) => `
        <button
          class="filter-chip${category === activeCategory ? " active" : ""}"
          type="button"
          data-category="${category}"
        >
          ${category}
        </button>
      `
    )
    .join("");

  filtersEl.querySelectorAll("[data-category]").forEach((button) => {
    button.addEventListener("click", () => {
      activeCategory = button.dataset.category;
      renderFilters();
      renderProducts();
    });
  });
}

function renderProducts() {
  const items = getFilteredItems();
  resultCountEl.textContent = `${items.length} shown`;

  productListEl.innerHTML = items
    .map((item) => {
      const status = stockStatus(item);
      const outOfStock = status.className === "out";
      return `
        <button
          class="product-card${outOfStock ? " out-of-stock" : ""}"
          type="button"
          data-id="${item.id}"
        >
          <h3>${item.name}</h3>
          <span class="stock-badge ${status.className}">${status.label}</span>
          <p class="meta">${item.category} · ${formatQuantity(item)} · ${formatPrice(item.price)}</p>
        </button>
      `;
    })
    .join("");

  emptyStateEl.hidden = items.length > 0;

  productListEl.querySelectorAll("[data-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = inventory.find((entry) => entry.id === button.dataset.id);
      if (item) {
        openDetail(item);
      }
    });
  });
}

function openDetail(item) {
  const status = stockStatus(item);
  detailCategoryEl.textContent = item.category;
  detailTitleEl.textContent = item.name;
  detailBodyEl.innerHTML = [
    ["Stock status", status.label],
    ["On hand", formatQuantity(item)],
    ["Unit cost", formatPrice(item.price)],
    ["Min level", item.minLevel ?? "Not set"],
    ["Ordered", item.ordered || "0"],
    ["SKU / SID", item.id || "—"],
    ["Notes", item.notes || "—"],
  ]
    .map(
      ([label, value]) => `
        <div class="detail-row">
          <span>${label}</span>
          <strong>${value}</strong>
        </div>
      `
    )
    .join("");

  sheetBackdrop.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeDetail() {
  sheetBackdrop.hidden = true;
  document.body.style.overflow = "";
}

searchInput.addEventListener("input", (event) => {
  query = event.target.value;
  clearSearchButton.hidden = query.length === 0;
  renderProducts();
});

clearSearchButton.addEventListener("click", () => {
  query = "";
  searchInput.value = "";
  clearSearchButton.hidden = true;
  searchInput.focus();
  renderProducts();
});

closeDetailButton.addEventListener("click", closeDetail);
sheetBackdrop.addEventListener("click", (event) => {
  if (event.target === sheetBackdrop) {
    closeDetail();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !sheetBackdrop.hidden) {
    closeDetail();
  }
});

renderStats();
renderFilters();
renderProducts();
