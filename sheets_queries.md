# select 30 random
=Array_constrain(sort('title, abstract, doi'!A2:'title, abstract, doi'!C478,ArrayFormula(randbetween(row('title, abstract, doi'!A2:'title, abstract, doi'!C478)^0,9^9)),TRUE), 30, 3)