import { Suspense } from "react";
import Workbench from "@/components/Workbench";

export default function Page() {
  return (
    <Suspense>
      <Workbench />
    </Suspense>
  );
}
