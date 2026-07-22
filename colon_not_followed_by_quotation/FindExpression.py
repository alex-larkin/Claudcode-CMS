import patterns
import re

# Find all occurences of the expression that the user entered
# as Parameter1.

# Return true if input is valid
def validInput():
    global Parameter1

    if len(Parameter1) == 0:
        print "# You must enter an Expression to search for"
        return 0

    try:
        re.compile(Parameter1, re.UNICODE)
    except Exception, e:
        print "# Invalid Expression entered: " + e.args[0]
        return 0

    return 1    

    
# always do this first to initialize before running the check
patterns.setupCheck()


# Set up options
flags = re.MULTILINE | re.UNICODE    # make ^ apply at the beginning of every line
if MatchCase == "No":
    flags = flags | re.IGNORECASE
if DotAll == "Yes":
    flags = flags | re.DOTALL

if validInput():
    # tell patterns module to look pattern entered
    patterns.addPattern(Parameter1, " ")
    patterns.scanText(flags)

