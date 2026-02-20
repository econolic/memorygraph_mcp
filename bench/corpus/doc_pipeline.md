Pipeline RevenuePipeline consumes table finance.sales_daily and finance.refunds_daily.
RevenuePipeline writes into mart.revenue_fact.
Job RevenueReconcile depends on RevenuePipeline and calls Service Billing.
