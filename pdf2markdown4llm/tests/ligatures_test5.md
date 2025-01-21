Payroll Administrator Guide
Percent: Applied as a percentage of the taxable wage. This is the default option.
Flat: Applied as a fixed dollar amount regardless of the taxable wage. You can use the
option, for example, if the pay is always the same.
### Table

| i Eective From Eective To | The time period in which the tax override for earnings is applied. By default, the current date s displayed in the Eective From field, but you can select a dierent date as needed. Seing a date in the Eective To field is optional. : You can set the Eective From field to a date in the past to apply the flat tax override to uncommied payroll data from that period. For example, if there is already payroll data created for the current pay period that started last week, you could set the Eective From field to a week in the past. |
|:---:|:---:|

The override amount that is applied in based on the calculation method selected in
Federal Amount
Amount Type. A single override can have a value defined in one or both fields. When one of
the fields is le blank that tax continues to be calculated using the standard formula and all
Provincial
other factors.
Amount
Provincial Amount is only available in Canadian employee records. State Amount is only
State Amount
available in US employee records.
Example of Flat Tax Configuration
: While this example includes a US employee, the functionality described is also applicable for Canadian
employees.
You create a quick entry on an o-cycle pay run using a custom check template called Secondary Check.
withholds $193.80 (approximately 13%) in federal taxes for the entry, as shown in the following example:
To configure to withhold 25% in federal income tax on these earnings for the employee, you first need to
ensure that the check template used for the payroll entry has flat tax enabled. Go to Payroll Setup > Check Templates,
select the custom template , and select the Allow Flat Tax checkbox for the country of the employee,
in this case the US. The Allow Flat Tax checkbox is shown in the following screenshot:
Page 961 of 1226
