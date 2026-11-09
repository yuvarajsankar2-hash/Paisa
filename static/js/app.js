(() => {
  const toggle = document.getElementById("account-toggle");
  const menu = document.getElementById("account-menu");

  if (toggle && menu) {
    const closeMenu = () => {
      menu.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    };

    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      menu.hidden = !menu.hidden;
      toggle.setAttribute("aria-expanded", String(!menu.hidden));
    });

    menu.addEventListener("click", (event) => event.stopPropagation());
    document.addEventListener("click", closeMenu);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeMenu();
        toggle.focus();
      }
    });
  }

  const chartData = window.paisaChartData;
  const canvas = document.getElementById("overview-chart");
  if (canvas && chartData && window.Chart) {
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: chartData.labels,
        datasets: [
          {
            label: "Money in",
            data: chartData.credits,
            backgroundColor: "#4b9b79",
            borderRadius: 5,
            maxBarThickness: 26,
          },
          {
            label: "Money out",
            data: chartData.debits,
            backgroundColor: "#e7a577",
            borderRadius: 5,
            maxBarThickness: 26,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) =>
                `${context.dataset.label}: ₹${context.parsed.y.toLocaleString("en-IN", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}`,
            },
          },
        },
        scales: {
          x: { grid: { display: false }, border: { display: false } },
          y: {
            beginAtZero: true,
            border: { display: false, dash: [3, 5] },
            grid: { color: "#edf0f5" },
            ticks: {
              callback: (value) => `₹${Number(value).toLocaleString("en-IN")}`,
            },
          },
        },
      },
    });
  }
})();
