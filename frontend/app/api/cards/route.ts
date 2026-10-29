import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

export async function GET() {
  const cardsPath = path.join(process.cwd(), "..", "data", "cards.json");

  try {
    const contents = await readFile(cardsPath, "utf8");
    const document: unknown = JSON.parse(contents);
    if (
      !document ||
      typeof document !== "object" ||
      !Array.isArray((document as { cards?: unknown }).cards)
    ) {
      return NextResponse.json({ error: "Card data has an invalid format." }, { status: 500 });
    }
    return NextResponse.json(document, {
      headers: { "Cache-Control": "no-store, max-age=0" },
    });
  } catch (error) {
    console.error("Could not load data/cards.json", error);
    return NextResponse.json({ error: "Card data is unavailable." }, { status: 500 });
  }
}