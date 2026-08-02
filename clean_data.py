import pandas as pd
import numpy as np

print("Libraries imported successfully!")


df = pd.read_csv("Comcast.csv")

print(df.head())

print(df.info())

print(df.isnull().sum())

print("Duplicates:", df.duplicated().sum())

df = df.drop_duplicates()

#remove-extra-space
for col in df.select_dtypes(include=["object", "string"]).columns:
    df[col] = (
        df[col]
        .astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )
#standardize-text-case
    df["City"] = df["City"].str.title()

df["State"] = df["State"].str.title()

df["Received Via"] = df["Received Via"].str.title()

df["Status"] = df["Status"].str.title()

df["Filing on Behalf of Someone"] = (
    df["Filing on Behalf of Someone"].str.title()
)

df["Customer Complaint"] = (
    df["Customer Complaint"]
    .str.strip()
    .str.replace(r"\s+", " ", regex=True)
)

#date
# print(df["Date"].head(10))
# print(df["Date_month_year"].head(10))
df["Date"] = pd.to_datetime(
    df["Date"],
    format="%d-%b-%y",
    errors="coerce"
)

df["Date_month_year"] = pd.to_datetime(
    df["Date_month_year"],
    format="%d-%b-%y",
    errors="coerce"
)

# Change all dates from 2015 to 2025
df["Date"] = df["Date"].apply(
    lambda x: x.replace(year=2025) if pd.notnull(x) else x
)

df["Date_month_year"] = df["Date_month_year"].apply(
    lambda x: x.replace(year=2025) if pd.notnull(x) else x
)

#print(df["Time"].head()) #Checktimeformat
df["Time"] = pd.to_datetime(
    df["Time"],
    format="%I:%M:%S %p",
    errors="coerce"
).dt.time #forTime

df["Zip code"] = (
    pd.to_numeric(df["Zip code"], errors="coerce")
    .fillna(0)
    .astype(int)
)#Convert-zipcode

df = df.drop_duplicates(subset="Ticket #")

df["Complaint_Clean"] = (
    df["Customer Complaint"]
    .str.lower()
    .str.replace(r"[^\w\s]", "", regex=True)
    .str.replace(r"\s+", " ", regex=True)
    .str.strip()
)

#Checkfinaldata
print(df.head())

print(df.info())

print(df.describe(include="all"))

df.to_csv("Comcast_Cleaned.csv", index=False)

print("Cleaning completed successfully!")