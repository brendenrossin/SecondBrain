import { AppShell } from "@/components/layout/AppShell";
import { ChatProvider } from "@/components/providers/ChatProvider";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ChatProvider>
      <AppShell>{children}</AppShell>
    </ChatProvider>
  );
}
