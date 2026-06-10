export default function AppShell({ sidebar, header, children }) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">{sidebar}</aside>
      <main className="app-main">
        {header}
        {children}
      </main>
    </div>
  );
}
