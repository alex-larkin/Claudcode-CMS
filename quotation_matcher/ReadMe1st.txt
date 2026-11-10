This tool was designed for the oteU project of Mexico where they are trying to make the quotation marks match the RVC.
I received permission to observe the RVCST project and used it as my base project for the tool.
The tool tries to match the «» first level quotation marks of the RVCST and insert them where appropriate in the target text.
Since the oteU does not use continuers at \q or \m it is necessary to run a regular expression (RegEx Pal) to remove those items.
Search for:
(\\m\s+(\\v \d+\s+)?)»
And replace with \1
The other search is:
(\\q\s+(\\v \d+\s+)?)»

After cleaning out these issues, there are still a large number of errors based on the use of continuers in the RVC where there are \p that do not exist in the oteU. As an example, this can be seen in Malachi 1 where the RVC has \p at verses 11 , 12, 14 and then chapter 2 verses 3, 5, 8 etc. The ote does not have paragraphs as these points.