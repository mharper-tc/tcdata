import pandas as pd
import tcdata

# A wide dataframe, exactly how an analyst would naturally build it:
# a date column plus one column per metric.
df = pd.DataFrame({
    "date":      ["2026-08-17", "2026-08-18"],
    "avg_price": [44.50, 44.80],
    "sku_count": [1910, 1915],
})

print("Pushing wide dataframe:")
print(df)

result = tcdata.push(dataset_id=1, df=df)
print("\nResult:", result)