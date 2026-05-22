from fastapi import FastAPI, Query

app = FastAPI(
    title="Mock Customer Lookup Agent",
    description="Local mock implementation of the customer lookup API.",
    version="1.0.0",
)


CUSTOMERS = [
    {
        "customer_id": "CUST-1001",
        "full_name": "Amit Kumar",
        "phone": "2016588874",
        "loyalty_points": 420,
        "preferred_store": "Fresh Basket Grocery - Jersey City",
    },
    {
        "customer_id": "CUST-1002",
        "full_name": "Priya Sharma",
        "phone": "5512228899",
        "loyalty_points": 185,
        "preferred_store": "Fresh Basket Grocery - Hoboken",
    },
    {
        "customer_id": "CUST-1003",
        "full_name": "Soumalya Chowdhury",
        "phone": "2016588874",
        "loyalty_points": 315,
        "preferred_store": "Fresh Basket Grocery - Jersey City",
    },
]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/customer-id")
async def customer_id(query: str = Query(..., min_length=2)) -> dict[str, object]:
    normalized_query = "".join(query.lower().split())

    for customer in CUSTOMERS:
        normalized_name = "".join(customer["full_name"].lower().split())
        normalized_phone = "".join(str(customer["phone"]).split())
        if normalized_query == normalized_phone or normalized_query in normalized_name:
            return {"found": True, "query": query, **customer}

    return {
        "found": False,
        "query": query,
        "message": "No matching customer was found for the supplied phone number or full name.",
    }
